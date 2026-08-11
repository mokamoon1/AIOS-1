"""Paper Trading end-to-end integration tests (AIOS-407, AIOS-406 section 13).

Booting the Core Engine in the Paper environment wires the authorized Paper
Broker (AIOS-603 section 11). An approved decision is routed through the
coordinator into a PENDING paper order, filled explicitly, and persisted
through the Data Layer facade; the Performance Tracking service then reports
objective metrics computed from the recorded data (AIOS-308 section 12).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import aios.core.engine as core_module
import aios.database.models  # noqa: F401  (register ORM models on Base.metadata)
from aios.agents.permissions import Role
from aios.brokers.models import OrderStatus
from aios.config import Environment
from aios.core import CoreEngine
from aios.data.models import DecisionAction, InvestmentDecision
from aios.database.base import Base
from aios.database.repositories import (
    BrokerAccountRepository,
    DecisionRepository,
    PaperFillRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)
from aios.performance import PerformanceService

pytestmark = pytest.mark.integration

_UTC = timezone.utc


def _sqlite_engine():
    """In-memory SQLite engine with the full AIOS schema (ADR-0001)."""
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


def _approved_buy_decision() -> InvestmentDecision:
    return InvestmentDecision(
        symbol="AAPL",
        decision=DecisionAction.BUY,
        reason="approved buy",
        confidence=1.0,
        risk_score=0.2,
        timestamp=datetime(2026, 8, 1, 12, 0, tzinfo=_UTC),
        supporting_data={
            "validation": {
                "shariah_approval": True,
                "data_availability": True,
                "analysis_completion": True,
                "risk_approval": True,
            }
        },
    )


def _market_open_clock() -> datetime:
    """Deterministic 'now' inside US market hours (2026-08-06 10:00 EDT)."""
    return datetime(2026, 8, 6, 14, 0, tzinfo=_UTC)


async def _boot_core(monkeypatch: pytest.MonkeyPatch, environment: Environment) -> CoreEngine:
    """Boot a Core Engine against in-memory SQLite without file logging."""
    monkeypatch.setattr(core_module, "create_db_engine", lambda url, **kwargs: _sqlite_engine())
    monkeypatch.setattr(core_module, "setup_logging", lambda settings: logging.getLogger("aios"))
    monkeypatch.setattr(
        core_module, "setup_audit_handler", lambda logger: logging.getLogger("aios.audit")
    )
    core = CoreEngine(environment=environment, clock=_market_open_clock)
    await core.start()
    return core


async def test_paper_environment_wires_authorized_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = await _boot_core(monkeypatch, Environment.PAPER)
    try:
        assert core.is_ready()
        assert core.broker_service is not None
        assert core.paper_coordinator is not None
        assert core.broker_service.broker_id == "paper"
    finally:
        await core.shutdown()


async def test_approved_decision_flows_to_order_fill_and_performance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = await _boot_core(monkeypatch, Environment.PAPER)
    try:
        session_factory = core.session_factory
        DecisionRepository(session_factory).add_decisions([_approved_buy_decision()])

        coordinator = core.paper_coordinator
        broker_service = core.broker_service
        assert coordinator is not None and broker_service is not None

        order = coordinator.submit_for_decision(
            "AAPL",
            exchange="NASDAQ",
            quantity=10.0,
            price=100.0,
            role=Role.TRADING,
        )
        assert order.status is OrderStatus.PENDING
        assert broker_service.get_order(order.order_id).status is OrderStatus.PENDING
        assert len(PaperOrderRepository(session_factory).list_orders()) == 1

        filled, fill = broker_service.fill_order(order.order_id, price=100.0, role=Role.TRADING)
        assert filled.status is OrderStatus.FILLED
        assert fill.quantity == 10.0
        assert fill.realized_pnl == 0.0

        stored_order = PaperOrderRepository(session_factory).get_order(order.order_id)
        assert stored_order.status is OrderStatus.FILLED
        assert stored_order.decision_ref == "AAPL:2026-08-01T12:00:00+00:00"

        fills = PaperFillRepository(session_factory).list_fills()
        assert len(fills) == 1
        positions = PaperPositionRepository(session_factory).list_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10.0

        account = BrokerAccountRepository(session_factory).get_account("paper")
        assert account.cash == pytest.approx(99_000.0)

        snapshot = PerformanceService().build_snapshot(
            account=account,
            orders=PaperOrderRepository(session_factory).list_orders(),
            fills=fills,
            positions=positions,
        )
        assert snapshot.order_count == 1
        assert snapshot.fill_count == 1
        assert snapshot.position_count == 1
        assert snapshot.market_value == pytest.approx(1_000.0)
        assert snapshot.equity == pytest.approx(100_000.0)
        assert snapshot.total_return_pct == pytest.approx(0.0)
    finally:
        await core.shutdown()


async def test_broker_never_wired_outside_paper_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = await _boot_core(monkeypatch, Environment.TESTING)
    try:
        assert core.broker_service is None
        assert core.paper_coordinator is None
    finally:
        await core.shutdown()
