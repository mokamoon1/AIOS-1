"""AIOS V1 Operational Validation Test (Tests 1-14).

End-to-end operational validation of the AIOS V1 platform running in the
Paper Trading environment against a real (SQLite) database created through
the Alembic migrations. This is NOT a pytest suite: it boots the live Core
Engine, seeds verified data through the Database Layer repositories, and
drives the documented workflows (analysis, Shariah gate, risk gate, paper
ordering, persistence, performance, monitoring, security, restart recovery).

Scope and prohibitions (aligned with the accepted V1 completion):
    * Paper Trading only (AIOS-208 section 8). No live broker, no real
      money, no Alpaca SDK, no API keys.
    * No source-code modification is made by this script; it exercises the
      shipped system and reports actual observations.
    * No new strategy, threshold, risk limit, or position-sizing rule is
      introduced.

Exit code: 0 when every test passes; 1 when any test fails. A human-readable
run log is written to logs/operational_validation.txt.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Environment: must be set before any aios.config read (get_environment() /
# load_settings() / Alembic env.py resolve at call time).
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "logs" / "operational_validation.db"
DB_URL = "sqlite:///" + str(DB_PATH).replace("\\", "/")
AIOS_LOG = ROOT / "logs" / "aios.log"
REPORT_LOG = ROOT / "logs" / "operational_validation.txt"

os.environ.setdefault("AIOS_ENVIRONMENT", "paper")
os.environ.setdefault("AIOS_DATABASE_URL", DB_URL)

# ---------------------------------------------------------------------------
# Imports (after environment setup; the alembic env reads the env vars).
# ---------------------------------------------------------------------------
from alembic import command as alembic_command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402

from aios.agents.messages import AgentContext  # noqa: E402
from aios.agents.permissions import Role  # noqa: E402
from aios.agents.types import AgentType  # noqa: E402
from aios.brokers.exceptions import BrokerValidationError  # noqa: E402
from aios.brokers.models import OrderSide, OrderStatus, PaperOrder  # noqa: E402
from aios.config import Environment  # noqa: E402
from aios.core import CoreEngine, CoreState  # noqa: E402
from aios.data.models import (  # noqa: E402
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    DecisionAction,
    InvestmentDecision,
    MarketStatus,
    PortfolioPosition,
    PositionStatus,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.data.pipeline import DataPipeline  # noqa: E402
from aios.data.services import DataService  # noqa: E402
from aios.data.validation import DataValidator  # noqa: E402
from aios.database.repositories import (  # noqa: E402
    BrokerAccountRepository,
    CompanyRepository,
    DecisionRepository,
    MarketRepository,
    PaperFillRepository,
    PaperOrderRepository,
    PaperPositionRepository,
    PortfolioRepository,
    ShariahRepository,
)
from aios.engines.exceptions import EngineValidationError  # noqa: E402
from aios.engines.messages import EngineInput  # noqa: E402
from aios.engines.roster import require_decision_authority  # noqa: E402
from aios.engines.types import EngineType  # noqa: E402
from aios.errors import EngineError, SecurityError  # noqa: E402
from aios.events import Event  # noqa: E402
from aios.monitoring import HealthMonitor  # noqa: E402
from aios.performance import PerformanceService  # noqa: E402
from aios.portfolio import PortfolioService  # noqa: E402

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers: domain model factories for seeded data.
# ---------------------------------------------------------------------------
def candle(symbol: str, index: int) -> Candle:
    """A daily candle for ``symbol`` with a slight uptrend."""
    close = 10.0 + index * 0.5
    return Candle(
        timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=UTC) + timedelta(days=index),
        symbol=symbol,
        timeframe=Timeframe.ONE_DAY,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1000.0,
    )


def compliance(
    symbol: str,
    company: str,
    status: ComplianceStatus,
    *,
    exchange: str = "NASDAQ",
) -> ShariahCompliance:
    """A Shariah compliance record for ``symbol`` with the given status."""
    return ShariahCompliance(
        symbol=symbol,
        company_name=company,
        exchange=exchange,
        country="US",
        asset_type=AssetType.EQUITY,
        compliance_status=status,
        provider="validation",
        review_date=date(2026, 1, 1),
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31),
        screening_methodology="validation",
        screening_date=date(2026, 1, 1),
    )


def fundamentals(symbol: str, *, sector: str = "Technology", revenue: float = 1000.0) -> CompanyFundamentals:
    """Fundamental figures for ``symbol``."""
    return CompanyFundamentals(
        symbol=symbol,
        sector=sector,
        industry="Software",
        revenue=revenue,
        net_income=150.0,
        eps=1.5,
        assets=2000.0,
        liabilities=800.0,
        cash_flow=250.0,
        equity=1200.0,
        report_date=date(2026, 6, 30),
    )


def open_position(
    symbol: str,
    quantity: float,
    allocation: float,
    *,
    entry: float = 100.0,
    current: float | None = None,
    sector: str = "Technology",
) -> PortfolioPosition:
    """An open portfolio position for ``symbol``."""
    price = current if current is not None else entry
    return PortfolioPosition(
        symbol=symbol,
        exchange="NASDAQ",
        quantity=quantity,
        entry_price=entry,
        current_price=price,
        allocation=allocation,
        sector=sector,
        status=PositionStatus.OPEN,
        updated_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    )


def approved_decision(
    symbol: str,
    decision: DecisionAction,
    *,
    timestamp: datetime | None = None,
    risk_score: float = 0.2,
) -> InvestmentDecision:
    """An approved decision carrying all four documented validation gates.

    The default timestamp is in the future so the decision is always the
    latest for its symbol (the Paper Order Coordinator routes the most recent
    decision only).
    """
    return InvestmentDecision(
        symbol=symbol,
        decision=decision,
        reason=f"approved {decision.value} decision",
        confidence=1.0,
        risk_score=risk_score,
        timestamp=timestamp or datetime(2027, 1, 1, 12, 0, tzinfo=UTC),
        supporting_data={
            "validation": {
                "shariah_approval": True,
                "data_availability": True,
                "analysis_completion": True,
                "risk_approval": True,
            }
        },
    )


def build_data_service(session_factory: Any) -> DataService:
    """Build the Data Layer facade over the startup session factory.

    Mirrors the wiring performed by the Core Engine (``_build_data_access``)
    so the validation reads through the same public repositories.
    """
    return DataService(
        DataPipeline(DataValidator()),
        market_repository=MarketRepository(session_factory),
        shariah_repository=ShariahRepository(session_factory),
        fundamental_repository=CompanyRepository(session_factory),
        portfolio_repository=PortfolioRepository(session_factory),
        decision_repository=DecisionRepository(session_factory),
        paper_order_repository=PaperOrderRepository(session_factory),
        paper_fill_repository=PaperFillRepository(session_factory),
        paper_position_repository=PaperPositionRepository(session_factory),
        broker_account_repository=BrokerAccountRepository(session_factory),
    )


# ---------------------------------------------------------------------------
# Test harness.
# ---------------------------------------------------------------------------
class ErrorRecorder:
    """Collects ERROR events published on the Event Bus."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    async def handle(self, event: Event) -> None:
        if event.event_type == "ERROR":
            self.events.append(event)


class Context:
    """Shared state across the operational tests."""

    def __init__(self) -> None:
        self.core: CoreEngine | None = None
        self.data: DataService | None = None
        self.engine: dict[EngineType, Any] = {}
        self.results: list[dict[str, Any]] = []


def _market_open_clock() -> datetime:
    """Deterministic 'now' inside US market hours (2026-08-06 10:00 EDT).

    The market-session guard (Phase 9.6, P0-5) reads the clock it is given;
    booting the validation harness with a fixed market-open time keeps the
    14 operational checks independent of the wall-clock time of day.
    """
    return datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)


async def boot_core() -> CoreEngine:
    """Boot a live Core Engine in the Paper environment (real config/logging/DB)."""
    core = CoreEngine(environment=Environment.PAPER, clock=_market_open_clock)
    await core.start()
    return core


def run(test_number: int, name: str):
    """Wrap an async test procedure, recording PASS/FAIL."""

    def decorate(coro):
        async def runner(ctx: Context) -> dict[str, Any]:
            record: dict[str, Any] = {"number": test_number, "name": name}
            try:
                notes = await coro(ctx)
                record["passed"] = True
                record["notes"] = notes or []
            except Exception as exc:  # noqa: BLE001 - harness boundary
                record["passed"] = False
                record["error"] = f"{type(exc).__name__}: {exc}"
            ctx.results.append(record)
            return record

        return runner

    return decorate


# ---------------------------------------------------------------------------
# Tests 1-14.
# ---------------------------------------------------------------------------
@run(1, "Startup (Paper environment)")
async def test_01_startup(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    assert core.is_ready(), "Core Engine must reach READY"
    assert core.state is CoreState.READY
    assert core.settings is not None and core.settings.environment is Environment.PAPER
    assert core.broker_service is not None, "Paper Broker must be wired in Paper env"
    assert core.paper_coordinator is not None, "Paper Order Coordinator must be wired"
    assert core.broker_service.broker_id == "paper"
    agents = core.agent_manager.list_agents()
    engines = core.engine_manager.list_engines()
    assert len(agents) == 8, f"expected 8 agents, got {len(agents)}"
    assert len(engines) == 6, f"expected 6 engines, got {len(engines)}"
    assert core.status()["state"] == "ready"
    assert AIOS_LOG.is_file(), "Paper environment must write a JSON log file"
    lines = AIOS_LOG.read_text(encoding="utf-8").splitlines()
    assert any(line.strip() for line in lines), "JSON log file must not be empty"
    return [
        f"Core Engine READY in paper environment",
        f"Broker 'paper' wired with coordinator",
        f"Agents loaded: {len(agents)}; Engines loaded: {len(engines)}",
        f"JSON log file present: {AIOS_LOG.name}",
    ]


@run(2, "Health / status reporting")
async def test_02_health(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    metrics = [engine.metrics() for engine in core.engine_manager.list_engines()]
    snapshot = HealthMonitor().snapshot(core.status(), engine_metrics=metrics)
    assert snapshot.environment == "paper"
    assert snapshot.state == "ready"
    assert snapshot.service_available is True
    assert snapshot.data_available is True
    assert snapshot.broker_connected is True
    # Phase 7: Provider Module activated - 4 mock providers expected in PAPER/TESTING (including News)
    assert snapshot.providers_connected == 4, (
        f"expected 4 connected mock providers, got {snapshot.providers_connected}"
    )
    assert snapshot.agent_loaded == 8 and snapshot.agent_ready == 8
    assert snapshot.engine_loaded == 6 and snapshot.engine_ready == 6
    return [
        f"service_available={snapshot.service_available}",
        f"data_available={snapshot.data_available} broker_connected={snapshot.broker_connected}",
        f"agents={snapshot.agent_loaded}/{snapshot.agent_ready} "
        f"engines={snapshot.engine_loaded}/{snapshot.engine_ready}",
        f"providers_connected={snapshot.providers_connected}",
    ]


@run(3, "Data Flow (DB -> repository -> DataService facade -> engine)")
async def test_03_data_flow(ctx: Context) -> list[str]:
    data = ctx.data
    core = ctx.core
    assert data is not None and core is not None
    candles = data.get_candles("AAPL", Timeframe.ONE_DAY)
    assert len(candles) == 40, f"expected 40 AAPL candles, got {len(candles)}"
    security = data.get_security("AAPL", "NASDAQ")
    assert security.symbol == "AAPL" and security.exchange == "NASDAQ"
    compliance_status = data.get_compliance_status("AAPL")
    assert compliance_status.compliance_status is ComplianceStatus.COMPLIANT
    fundamental = data.get_fundamentals("AAPL")
    assert fundamental.revenue == 1000.0
    market_engine = ctx.engine[EngineType.MARKET]
    result = await core.engine_manager.execute(
        market_engine.engine_id,
        EngineInput(request_id="op-3", payload={"symbol": "AAPL"}),
    )
    assert result.output["bars"] == 40, "engine must read candles through the facade"
    return [
        "Candles, security, compliance, and fundamentals readable via DataService",
        f"Market Engine consumed {result.output['bars']} bars through the facade",
    ]


@run(4, "Shariah Gate (only compliant securities enter analysis)")
async def test_04_shariah_gate(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    market_engine = ctx.engine[EngineType.MARKET]
    for symbol in ("WINE", "UNKW"):
        try:
            await core.engine_manager.execute(
                market_engine.engine_id,
                EngineInput(request_id=f"op-4-{symbol}", payload={"symbol": symbol}),
            )
        except EngineValidationError as exc:
            assert "not Shariah-approved" in str(exc) or "analysis blocked" in str(exc)
        else:
            assert False, f"analysis of non-compliant {symbol} must be blocked"
        market_engine.reset()
    result = await core.engine_manager.execute(
        market_engine.engine_id,
        EngineInput(request_id="op-4-apl", payload={"symbol": "AAPL"}),
    )
    assert result.output["symbol"] == "AAPL"
    market_engine.reset()
    return [
        "NON_COMPLIANT (WINE) and UNKNOWN (UNKW) securities blocked from analysis",
        "COMPLIANT (AAPL) security passes the gate",
    ]


@run(5, "Analysis Engines (Market / Technical / Fundamental / Decision)")
async def test_05_analysis(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    input_market = EngineInput(request_id="op-5-market", payload={"symbol": "MSFT"})
    market = await core.engine_manager.execute_by_type(EngineType.MARKET, input_market)
    assert market.output["symbol"] == "MSFT"
    assert market.output["market_bias"] in {"bullish", "bearish", "neutral"}
    assert market.output["market_score"] >= 0
    assert market.output["volatility"]["atr_14"] > 0

    technical = await core.engine_manager.execute_by_type(
        EngineType.TECHNICAL,
        EngineInput(request_id="op-5-tech", payload={"symbol": "MSFT"}),
    )
    assert technical.output["indicators"]["sma_20"] is not None
    assert technical.output["indicators"]["rsi_14"] is not None
    assert "direction" in technical.output["structure"]

    fundamental = await core.engine_manager.execute_by_type(
        EngineType.FUNDAMENTAL,
        EngineInput(request_id="op-5-fund", payload={"symbol": "MSFT"}),
    )
    assert fundamental.output["metrics"]["revenue"] == 1000.0
    assert "net_margin" in fundamental.output["derived_ratios"]

    pipeline_input = EngineInput(
        request_id="op-5-pipeline",
        payload={
            "symbol": "MSFT",
            "timeframe": "1d",
            "max_position_percentage": 10.0,
            "max_sector_exposure": 25.0,
            "portfolio_value": 100_000.0,
            "requested_position_percentage": 2.0,
        },
    )
    results = await core.engine_manager.run_pipeline(list(EngineType), pipeline_input)
    decision = results[EngineType.DECISION]
    # Decision Engine now produces directional decision (BUY/SELL/HOLD) when all gates pass
    assert decision.output["decision"] in {"buy", "sell", "hold"}, (
        f"expected directional decision, got {decision.output['decision']}"
    )
    assert decision.output["validation"]["status"] == "VALID"
    assert decision.output["persisted"] is True
    stored = DecisionRepository(core.session_factory).get_latest_decision("MSFT")
    assert stored.decision in {DecisionAction.BUY, DecisionAction.SELL, DecisionAction.HOLD}
    return [
        "Market, Technical, Fundamental engines produced objective outputs",
        "Decision pipeline: gates VALID -> directional decision, persisted to the decision log",
    ]


@run(6, "Portfolio Module (service snapshot + wired Portfolio Agent)")
async def test_06_portfolio(ctx: Context) -> list[str]:
    core = ctx.core
    data = ctx.data
    assert core is not None and data is not None
    snapshot = PortfolioService(reader=data).current_snapshot()
    assert snapshot.position_count == 2
    assert snapshot.total_value == pytest_approx(5_500.0 + 2_100.0)
    assert snapshot.sector_count == 1
    assert snapshot.sectors[0].sector == "Technology"
    assert snapshot.max_position_allocation == 0.05
    assert snapshot.weighted_return_pct == pytest_approx(0.05 * 10.0 + 0.02 * 5.0)

    portfolio_agent = core.agent_manager.get_by_type(AgentType.PORTFOLIO)[0]
    result = await portfolio_agent.execute(
        AgentContext(request_id="op-6", payload={"symbol": "AAPL"})
    )
    impact = result.output["portfolio_impact"]
    assert impact["position_count"] == 2
    return [
        "Portfolio snapshot: 2 positions, 1 sector, objective allocations",
        "Wired Portfolio Agent reported the current holdings view",
    ]


@run(7, "Risk Gate (configured limits enforced)")
async def test_07_risk_gate(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    approved_input = EngineInput(
        request_id="op-7-ok",
        payload={
            "symbol": "MSFT",
            "max_position_percentage": 10.0,
            "max_sector_exposure": 25.0,
            "portfolio_value": 100_000.0,
            "requested_position_percentage": 2.0,
        },
    )
    approved = await core.engine_manager.execute_by_type(EngineType.RISK, approved_input)
    assert approved.output["approval_status"] == "approved", approved.output
    assert approved.output["risk_level"] == "acceptable"
    assert approved.output["violations"] == []

    blocked_input = EngineInput(
        request_id="op-7-no",
        payload={
            "symbol": "MSFT",
            "max_position_percentage": 10.0,
            "max_sector_exposure": 25.0,
            "portfolio_value": 100_000.0,
            "requested_position_percentage": 50.0,
        },
    )
    blocked = await core.engine_manager.execute_by_type(EngineType.RISK, blocked_input)
    assert blocked.output["approval_status"] == "blocked", blocked.output
    assert blocked.output["risk_level"] == "rejected"
    assert blocked.output["violations"], "a configured-limit violation must be reported"

    decision_results = await core.engine_manager.run_pipeline(
        list(EngineType),
        EngineInput(
            request_id="op-7-dec",
            payload={
                "symbol": "MSFT",
                "max_position_percentage": 10.0,
                "max_sector_exposure": 25.0,
                "portfolio_value": 100_000.0,
                "requested_position_percentage": 50.0,
            },
        ),
    )
    decision = decision_results[EngineType.DECISION]
    assert decision.output["decision"] == "no_trade", (
        "a blocked risk limit must never produce an actionable decision"
    )
    assert decision.output["validation"]["checks"]["risk_approval"] is False
    return [
        "Within limits: approval_status=approved, no violations",
        "Over limits: approval_status=blocked with documented violations",
        "Blocked risk propagates to Decision -> NO_TRADE (no forced trading)",
    ]


@run(8, "Paper Ordering (SUBMIT_PAPER_ORDERS + explicit lifecycle)")
async def test_08_paper_orders(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    coordinator = core.paper_coordinator
    broker = core.broker_service
    assert coordinator is not None and broker is not None
    session_factory = core.session_factory

    # Permission is enforced before any execution.
    buy_decision = approved_decision("MSFT", DecisionAction.BUY)
    DecisionRepository(session_factory).add_decisions([buy_decision])
    try:
        coordinator.submit_for_decision(
            "MSFT", exchange="NASDAQ", quantity=10.0, price=100.0, role=Role.ANALYST
        )
    except SecurityError as exc:
        assert "submit_paper_orders" in str(exc)
    else:
        assert False, "ANALYST role must not submit paper orders"

    order_a = coordinator.submit_for_decision(
        "MSFT", exchange="NASDAQ", quantity=10.0, price=100.0, role=Role.TRADING
    )
    assert order_a.status is OrderStatus.PENDING
    assert order_a.decision_ref is not None
    assert len(PaperOrderRepository(session_factory).list_orders()) == 1

    try:
        broker.fill_order(order_a.order_id, price=100.0, role=Role.ANALYST)
    except SecurityError:
        pass
    else:
        assert False, "ANALYST role must not fill paper orders"

    filled_a, fill_a = broker.fill_order(order_a.order_id, price=100.0, role=Role.TRADING)
    assert filled_a.status is OrderStatus.FILLED
    assert fill_a.realized_pnl == 0.0
    account = broker.check_account()
    assert account.cash == 99_000.0
    positions = broker.get_positions()
    assert any(p.symbol == "MSFT" and p.quantity == 10.0 for p in positions)

    # A second fill on a FILLED order is invalid.
    try:
        broker.fill_order(order_a.order_id, price=100.0, role=Role.TRADING)
    except Exception as exc:
        assert "only PENDING" in str(exc)
    else:
        assert False, "double fill of a FILLED order must be rejected"

    # Sell leg: realize P&L (routed directly with an explicit SELL decision).
    sell_decision = approved_decision(
        "MSFT", DecisionAction.SELL, timestamp=datetime(2027, 1, 2, 12, 0, tzinfo=UTC)
    )
    DecisionRepository(session_factory).add_decisions([sell_decision])
    order_b = broker.submit_paper_order(
        PaperOrder(
            order_id="op-sell-1",
            broker_id=broker.broker_id,
            symbol="MSFT",
            exchange="NASDAQ",
            side=OrderSide.SELL,
            quantity=4.0,
            price=110.0,
        ),
        decision=sell_decision,
        role=Role.TRADING,
    )
    filled_b, fill_b = broker.fill_order(order_b.order_id, price=110.0, role=Role.TRADING)
    assert filled_b.status is OrderStatus.FILLED
    assert fill_b.realized_pnl == 40.0
    assert broker.check_account().cash == 99_440.0
    msft = next(p for p in broker.get_positions() if p.symbol == "MSFT")
    assert msft.quantity == 6.0

    # Cancel and reject paths (direct service submission, BUY decisions).
    buy_decision_c = approved_decision(
        "MSFT", DecisionAction.BUY, timestamp=datetime(2027, 1, 3, 12, 0, tzinfo=UTC)
    )
    order_c = broker.submit_paper_order(
        PaperOrder(
            order_id="op-cancel-1",
            broker_id=broker.broker_id,
            symbol="MSFT",
            exchange="NASDAQ",
            side=OrderSide.BUY,
            quantity=5.0,
            price=100.0,
        ),
        decision=buy_decision_c,
        role=Role.TRADING,
    )
    cancelled = broker.cancel_order(order_c.order_id, role=Role.TRADING)
    assert cancelled.status is OrderStatus.CANCELLED

    buy_decision_d = approved_decision(
        "MSFT", DecisionAction.BUY, timestamp=datetime(2027, 1, 4, 12, 0, tzinfo=UTC)
    )
    order_d = broker.submit_paper_order(
        PaperOrder(
            order_id="op-reject-1",
            broker_id=broker.broker_id,
            symbol="MSFT",
            exchange="NASDAQ",
            side=OrderSide.BUY,
            quantity=5.0,
            price=100.0,
        ),
        decision=buy_decision_d,
        role=Role.TRADING,
    )
    rejected = broker.reject_order(order_d.order_id, reason="policy reject", role=Role.TRADING)
    assert rejected.status is OrderStatus.REJECTED

    return [
        "ANALYST role denied SUBMIT_PAPER_ORDERS (submit and fill)",
        "submit -> PENDING (no auto-fill); explicit fill -> FILLED",
        "Cash 100000 -> 99000 (buy 10@100) -> 99440 (sell 4@110); realized P&L 40",
        "PENDING -> CANCELLED and PENDING -> REJECTED explicit paths verified",
        "Double fill of a FILLED order rejected",
    ]


@run(9, "Persistence (orders / fills / positions / account / decisions)")
async def test_09_persistence(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    session_factory = core.session_factory

    orders = PaperOrderRepository(session_factory).list_orders()
    assert len(orders) == 4, f"expected 4 orders persisted, got {len(orders)}"
    filled = [o for o in orders if o.status is OrderStatus.FILLED]
    assert len(filled) == 2
    for order in filled:
        assert order.decision_ref is not None, "filled orders must carry a decision_ref"

    fills = PaperFillRepository(session_factory).list_fills()
    assert len(fills) == 2

    positions = PaperPositionRepository(session_factory).list_positions()
    msft = next(p for p in positions if p.symbol == "MSFT")
    assert msft.quantity == 6.0
    assert msft.entry_price == 100.0

    account = BrokerAccountRepository(session_factory).get_account("paper")
    assert account.cash == 99_440.0

    decisions = DecisionRepository(session_factory).get_decisions("MSFT")
    assert any(d.decision is DecisionAction.BUY for d in decisions)
    assert any(d.decision is DecisionAction.SELL for d in decisions)

    return [
        "4 paper orders persisted (2 FILLED, 1 CANCELLED, 1 REJECTED) with decision_ref",
        "2 fills, paper position MSFT qty=6 @ 100, broker account cash=99440",
        "Decision history for MSFT includes the BUY and SELL approvals",
    ]


@run(10, "Performance (objective snapshot from recorded data)")
async def test_10_performance(ctx: Context) -> list[str]:
    core = ctx.core
    data = ctx.data
    assert core is not None and data is not None
    snapshot = PerformanceService(reader=data).current_snapshot("paper")
    assert snapshot.order_count == 4
    assert snapshot.fill_count == 2
    assert snapshot.position_count == 1
    assert snapshot.cash == 99_440.0
    assert snapshot.market_value == 6.0 * 110.0
    assert snapshot.equity == pytest_approx(99_440.0 + 660.0)
    assert snapshot.realized_pnl == pytest_approx(40.0)
    assert snapshot.unrealized_pnl == pytest_approx((110.0 - 100.0) * 6.0)
    assert snapshot.total_pnl == pytest_approx(40.0 + 60.0)
    assert snapshot.total_return_pct == pytest_approx(100.0 / 100_000.0 * 100.0)
    return [
        "PerformanceService reported arithmetic metrics on recorded data",
        f"equity={snapshot.equity:.2f} total_pnl={snapshot.total_pnl:.2f} "
        f"return={snapshot.total_return_pct:.4f}%",
    ]


@run(11, "Monitoring (engine metrics + ERROR event observation)")
async def test_11_monitoring(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    metrics = [engine.metrics() for engine in core.engine_manager.list_engines()]
    assert sum(m["execution_count"] for m in metrics) > 0
    assert sum(m["failure_count"] for m in metrics) >= 0

    recorder = ErrorRecorder()
    core.bus.subscribe("ERROR", recorder.handle)
    market_engine = ctx.engine[EngineType.MARKET]
    try:
        await core.engine_manager.execute(
            market_engine.engine_id,
            EngineInput(request_id="op-11", payload={"symbol": "ZZZZ"}),
        )
    except EngineError:
        pass
    else:
        assert False, "engine on missing data must fail"
    assert recorder.events, "an ERROR event must be published on engine failure"
    error_payload = recorder.events[-1].payload
    assert error_payload["component"] == "Market Engine"
    market_engine.reset()

    health = HealthMonitor().snapshot(
        core.status(),
        engine_metrics=[engine.metrics() for engine in core.engine_manager.list_engines()],
        error_counts={"EngineError": 1},
    )
    assert health.performance["execution_count"] > 0
    assert health.error_counts["EngineError"] == 1
    return [
        "Engine metrics aggregate across the engine roster",
        "Engine failure published an ERROR event (component=Market Engine)",
        "HealthSnapshot carries performance and error dimensions",
    ]


@run(12, "Negative Security (7 controls)")
async def test_12_negative_security(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    coordinator = core.paper_coordinator
    broker = core.broker_service
    assert coordinator is not None and broker is not None
    session_factory = core.session_factory
    checked: list[str] = []

    # An approved AAPL BUY decision exists so the coordinator reaches the
    # authorization check for items 1-4.
    decision = approved_decision(
        "AAPL", DecisionAction.BUY, timestamp=datetime(2027, 2, 1, 12, 0, tzinfo=UTC)
    )
    DecisionRepository(session_factory).add_decisions([decision])

    # 1. Unauthorized submit.
    try:
        coordinator.submit_for_decision(
            "AAPL", exchange="NASDAQ", quantity=1.0, price=100.0, role=Role.ANALYST
        )
    except SecurityError:
        checked.append("unauthorized submit denied")
    else:
        assert False, "submit must require SUBMIT_PAPER_ORDERS"

    # 2-4. Unauthorized fill / cancel / reject.
    order = coordinator.submit_for_decision(
        "AAPL", exchange="NASDAQ", quantity=1.0, price=100.0, role=Role.TRADING
    )
    for operation in (
        ("fill", lambda: broker.fill_order(order.order_id, price=100.0, role=Role.ANALYST)),
        ("cancel", lambda: broker.cancel_order(order.order_id, role=Role.ANALYST)),
        ("reject", lambda: broker.reject_order(order.order_id, reason="x", role=Role.ANALYST)),
    ):
        try:
            operation[1]()
        except SecurityError:
            checked.append(f"unauthorized {operation[0]} denied")
        else:
            assert False, f"{operation[0]} must require SUBMIT_PAPER_ORDERS"
    broker.cancel_order(order.order_id, role=Role.TRADING)

    # 5. Only the Decision Engine may issue a recommendation.
    try:
        require_decision_authority(ctx.engine[EngineType.MARKET])
    except SecurityError:
        checked.append("decision authority enforced")
    else:
        assert False, "only the Decision Engine may issue recommendations"

    # 6. No forced trading: a non-actionable decision creates no order.
    hold_decision = approved_decision(
        "ORCL", DecisionAction.HOLD, timestamp=datetime(2027, 2, 2, 12, 0, tzinfo=UTC)
    )
    DecisionRepository(session_factory).add_decisions([hold_decision])
    try:
        coordinator.submit_for_decision(
            "ORCL", exchange="NASDAQ", quantity=1.0, price=100.0, role=Role.TRADING
        )
    except BrokerValidationError:
        checked.append("HOLD decision creates no order")
    else:
        assert False, "HOLD must not be forced into an order"

    # 7. The Broker is never wired outside the Paper environment.
    testing_core = CoreEngine(environment=Environment.TESTING)
    await testing_core.start()
    try:
        assert testing_core.broker_service is None
        assert testing_core.paper_coordinator is None
    finally:
        await testing_core.shutdown()
    checked.append("broker never wired outside paper")

    assert len(checked) == 7
    return checked


@run(13, "Restart / Recovery (persistence across restart)")
async def test_13_restart(ctx: Context) -> list[str]:
    core = ctx.core
    assert core is not None
    session_factory = core.session_factory
    assert PaperOrderRepository(session_factory).get_order("op-cancel-1").status is OrderStatus.CANCELLED

    await core.shutdown()
    ctx.core = None

    restarted = await boot_core()
    ctx.core = restarted
    ctx.data = build_data_service(restarted.session_factory)
    ctx.engine = {e.engine_type: e for e in restarted.engine_manager.list_engines()}

    assert restarted.is_ready()
    assert restarted.broker_service is not None
    session = restarted.session_factory
    assert len(PaperOrderRepository(session).list_orders()) == 5, (
        "5 orders (4 + 1 cancelled in T12) must survive restart"
    )
    fills = PaperFillRepository(session).list_fills()
    assert len(fills) == 2
    msft = next(p for p in PaperPositionRepository(session).list_positions() if p.symbol == "MSFT")
    assert msft.quantity == 6.0
    assert BrokerAccountRepository(session).get_account("paper").cash == 99_440.0
    assert DecisionRepository(session).get_latest_decision("MSFT").decision is DecisionAction.SELL
    candles = MarketRepository(session).get_candles("AAPL", Timeframe.ONE_DAY)
    assert len(candles) == 40
    return [
        "System rebooted cleanly to READY in the Paper environment",
        "Orders, fills, positions, account, decisions, and candles survived restart",
        "Observation: the PaperBroker instance is in-memory (AIOS-407); a fresh "
        "broker instance starts at initial cash while persisted records remain",
    ]


@run(14, "Full end-to-end flow (NVDA)")
async def test_14_end_to_end(ctx: Context) -> list[str]:
    core = ctx.core
    data = ctx.data
    assert core is not None and data is not None
    session_factory = core.session_factory

    # Seed verified data for a fresh symbol.
    MarketRepository(session_factory).add_candles(
        [candle("NVDA", i) for i in range(40)], provider="validation"
    )
    ShariahRepository(session_factory).add_records(
        [compliance("NVDA", "Nvidia", ComplianceStatus.COMPLIANT)]
    )
    CompanyRepository(session_factory).add_fundamentals([fundamentals("NVDA")])

    # Analysis pipeline -> persisted decision.
    pipeline = await core.engine_manager.run_pipeline(
        list(EngineType),
        EngineInput(
            request_id="op-14-pipeline",
            payload={
                "symbol": "NVDA",
                "max_position_percentage": 10.0,
                "max_sector_exposure": 25.0,
                "portfolio_value": 100_000.0,
                "requested_position_percentage": 3.0,
            },
        ),
    )
    decision_output = pipeline[EngineType.DECISION].output
    assert decision_output["validation"]["status"] == "VALID"
    # Decision Engine now produces directional decision (BUY/SELL/HOLD) when all gates pass
    assert decision_output["decision"] in {"buy", "sell", "hold"}
    stored_decision = DecisionRepository(session_factory).get_latest_decision("NVDA")
    assert stored_decision.decision in {DecisionAction.BUY, DecisionAction.SELL, DecisionAction.HOLD}

    # Downstream approval produces an actionable BUY decision.
    approved = approved_decision(
        "NVDA", DecisionAction.BUY, timestamp=datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
    )
    DecisionRepository(session_factory).add_decisions([approved])

    # Order routed and filled explicitly (never auto-filled).
    coordinator = core.paper_coordinator
    broker = core.broker_service
    assert coordinator is not None and broker is not None
    order = coordinator.submit_for_decision(
        "NVDA", exchange="NASDAQ", quantity=20.0, price=120.0, role=Role.TRADING
    )
    assert order.status is OrderStatus.PENDING
    filled, fill = broker.fill_order(order.order_id, price=120.0, role=Role.TRADING)
    assert filled.status is OrderStatus.FILLED
    assert fill.quantity == 20.0

    # End-to-end verification through the data and service layers.
    account = BrokerAccountRepository(session_factory).get_account("paper")
    assert account.cash == 99_440.0 - 20.0 * 120.0, (
        f"expected cash 97040 after NVDA buy, got {account.cash}"
    )
    positions = PaperPositionRepository(session_factory).list_positions()
    nvda = next(p for p in positions if p.symbol == "NVDA")
    assert nvda.quantity == 20.0, f"expected NVDA qty 20, got {nvda.quantity}"
    fills = PaperFillRepository(session_factory).list_fills()
    assert len(fills) == 3, f"expected 3 fills, got {len(fills)}"
    orders = PaperOrderRepository(session_factory).list_orders()
    assert len(orders) == 6, f"expected 6 orders, got {len(orders)}"

    performance = PerformanceService(reader=data).current_snapshot("paper")
    assert performance.fill_count == 3, f"expected 3 fills, got {performance.fill_count}"
    assert performance.position_count == 2, (
        f"expected 2 positions, got {performance.position_count}"
    )
    assert performance.market_value == pytest_approx(nvda.market_value + 6.0 * 110.0), (
        f"market_value mismatch: {performance.market_value} vs "
        f"{nvda.market_value + 6.0 * 110.0}"
    )
    assert performance.equity == pytest_approx(performance.cash + performance.market_value), (
        "equity must equal cash + market value"
    )

    portfolio = PortfolioService(reader=data).current_snapshot()
    assert portfolio.position_count == 2, (
        f"expected 2 portfolio positions, got {portfolio.position_count}"
    )
    health = HealthMonitor().snapshot(
        core.status(),
        engine_metrics=[e.metrics() for e in core.engine_manager.list_engines()],
    )
    assert health.service_available is True, "service must remain available"

    return [
        "NVDA: analysis pipeline -> VALID directional decision persisted in the decision log",
        "Approved BUY routed -> PENDING -> explicit FILLED (never auto-filled)",
        "Portfolio, performance, health, and persistence all consistent after the flow",
    ]


# ---------------------------------------------------------------------------
# Report and runner.
# ---------------------------------------------------------------------------
def pytest_approx(value: float) -> Any:
    """Tiny approx helper (the operational script has no pytest dependency)."""

    class _Approx:
        def __init__(self, expected: float) -> None:
            self._expected = float(expected)

        def __eq__(self, other: Any) -> bool:  # noqa: D105
            try:
                return abs(float(other) - self._expected) < 1e-6
            except (TypeError, ValueError):
                return False

        def __repr__(self) -> str:  # noqa: D105
            return f"approx({self._expected})"

    return _Approx(value)


async def prepare_database() -> None:
    """Create a fresh schema through the real Alembic migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.is_file():
        DB_PATH.unlink()
    if AIOS_LOG.is_file():
        AIOS_LOG.unlink()
    config = AlembicConfig(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    alembic_command.upgrade(config, "head")


def seed_repositories(ctx: Context) -> None:
    """Seed verified market, Shariah, fundamental, and portfolio data."""
    core = ctx.core
    assert core is not None
    session_factory = core.session_factory
    for symbol in ("AAPL", "WINE", "UNKW", "MSFT", "ORCL"):
        MarketRepository(session_factory).add_candles(
            [candle(symbol, i) for i in range(40)], provider="validation"
        )
        MarketRepository(session_factory).add_security(
            Security(
                symbol=symbol,
                exchange="NASDAQ",
                asset_type=AssetType.EQUITY,
                currency="USD",
                trading_session="regular",
                timezone="America/New_York",
                market_status=MarketStatus.OPEN,
            )
        )
    ShariahRepository(session_factory).add_records(
        [
            compliance("AAPL", "Apple", ComplianceStatus.COMPLIANT),
            compliance("WINE", "WineCo", ComplianceStatus.NON_COMPLIANT),
            compliance("UNKW", "UnknownCo", ComplianceStatus.UNKNOWN),
            compliance("MSFT", "Microsoft", ComplianceStatus.COMPLIANT),
            compliance("ORCL", "Oracle", ComplianceStatus.COMPLIANT),
        ]
    )
    CompanyRepository(session_factory).add_fundamentals(
        [
            fundamentals("AAPL"),
            fundamentals("MSFT"),
            fundamentals("ORCL"),
        ]
    )
    PortfolioRepository(session_factory).upsert_position(
        open_position("AAPL", 50.0, 0.05, entry=100.0, current=110.0)
    )
    PortfolioRepository(session_factory).upsert_position(
        open_position("MSFT", 20.0, 0.02, entry=100.0, current=105.0)
    )


def format_report(ctx: Context) -> str:
    """Render the operational validation report as text."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("AIOS V1 - OPERATIONAL VALIDATION TEST (Tests 1-14)")
    lines.append(f"Environment: {os.environ.get('AIOS_ENVIRONMENT')}")
    lines.append(f"Database:    {DB_URL}")
    lines.append(f"Started:     {datetime.now(UTC).isoformat()}")
    lines.append("=" * 78)
    passed = 0
    failed = 0
    for result in ctx.results:
        number = result["number"]
        name = result["name"]
        if result["passed"]:
            passed += 1
            lines.append(f"\n[{number:02d}] PASS - {name}")
            for note in result.get("notes", []):
                lines.append(f"      - {note}")
        else:
            failed += 1
            lines.append(f"\n[{number:02d}] FAIL - {name}")
            lines.append(f"      error: {result.get('error')}")
    lines.append("")
    lines.append("-" * 78)
    lines.append(f"TOTAL: {passed} passed, {failed} failed, {passed + failed} executed")
    lines.append("=" * 78)
    return "\n".join(lines)


async def main() -> int:
    print("Preparing database via Alembic migrations ...")
    await prepare_database()

    ctx = Context()
    ctx.core = await boot_core()
    ctx.data = build_data_service(ctx.core.session_factory)
    ctx.engine = {e.engine_type: e for e in ctx.core.engine_manager.list_engines()}
    seed_repositories(ctx)

    for procedure in (
        test_01_startup,
        test_02_health,
        test_03_data_flow,
        test_04_shariah_gate,
        test_05_analysis,
        test_06_portfolio,
        test_07_risk_gate,
        test_08_paper_orders,
        test_09_persistence,
        test_10_performance,
        test_11_monitoring,
        test_12_negative_security,
        test_13_restart,
        test_14_end_to_end,
    ):
        await procedure(ctx)

    if ctx.core is not None:
        await ctx.core.shutdown()

    report = format_report(ctx)
    print(report)
    REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    REPORT_LOG.write_text(report + "\n", encoding="utf-8")
    failed = sum(1 for result in ctx.results if not result["passed"])
    return 1 if failed else 0


if __name__ == "__main__":
    logging.getLogger("aios").setLevel(logging.WARNING)
    sys.exit(asyncio.run(main()))
