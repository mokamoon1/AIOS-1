"""Production-readiness system tests (Phase 6; AIOS-802, AIOS-807, AIOS-705).

These tests boot the full Core Engine across environments and verify the
documented Phase 6 readiness guarantees:

- environment separation and production configuration readiness (ADR-0009,
  AIOS-802): production carries no secrets in configuration, uses
  machine-readable file logging, and never auto-enables any broker.
- paper trading is the maximum execution level (AIOS-208 section 8,
  AIOS-603 section 11): no live broker is wired by the Core Engine and no
  live-broker adapter exists in the source tree.
- monitoring health snapshots derive strictly from reported state
  (AIOS-107 section 10, AIOS-807 section 7) and engine metrics
  (AIOS-605 section 16) without inventing thresholds.
- decision -> paper-order traceability is preserved end to end
  (AIOS-208 section 11, AIOS-907).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import aios.core.engine as core_module
import aios.database.models  # noqa: F401  (register ORM models on Base.metadata)
from aios.agents.permissions import Role
from aios.config import Environment
from aios.config.loader import TomlSettingsLoader
from aios.config.settings import LoggingDestination, LoggingFormat
from aios.core import CoreEngine
from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    DecisionAction,
    InvestmentDecision,
    ShariahCompliance,
    Timeframe,
)
from aios.database.base import Base
from aios.database.repositories import (
    CompanyRepository,
    DecisionRepository,
    MarketRepository,
    ShariahRepository,
)
from aios.engines.messages import EngineInput
from aios.engines.types import EngineType
from aios.monitoring import HealthMonitor

pytestmark = pytest.mark.system

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _sqlite_engine():
    """In-memory SQLite engine with the full AIOS schema (ADR-0001)."""
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


async def _boot_core(monkeypatch: pytest.MonkeyPatch, environment: Environment) -> CoreEngine:
    """Boot a Core Engine against in-memory SQLite without file logging."""
    monkeypatch.setattr(core_module, "create_db_engine", lambda url, **kwargs: _sqlite_engine())
    monkeypatch.setattr(core_module, "setup_logging", lambda settings: logging.getLogger("aios"))
    monkeypatch.setattr(
        core_module, "setup_audit_handler", lambda logger: logging.getLogger("aios.audit")
    )
    core = CoreEngine(environment=environment)
    await core.start()
    return core


def _candle(index: int) -> Candle:
    close = 10.0 + index * 0.5
    return Candle(
        timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc) + timedelta(days=index),
        symbol="AAPL",
        timeframe=Timeframe.ONE_DAY,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1000.0,
    )


def _compliance() -> ShariahCompliance:
    return ShariahCompliance(
        symbol="AAPL",
        company_name="Apple",
        exchange="NASDAQ",
        country="US",
        asset_type=AssetType.EQUITY,
        compliance_status=ComplianceStatus.COMPLIANT,
        provider="test",
        review_date=date(2026, 1, 1),
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31),
        screening_methodology="test",
        screening_date=date(2026, 1, 1),
    )


def _fundamentals() -> CompanyFundamentals:
    return CompanyFundamentals(
        symbol="AAPL",
        sector="Technology",
        revenue=1000.0,
        net_income=150.0,
        eps=1.5,
        assets=2000.0,
        liabilities=800.0,
        cash_flow=250.0,
        equity=1200.0,
        report_date=date(2026, 6, 30),
    )


def _approved_buy_decision() -> InvestmentDecision:
    return InvestmentDecision(
        symbol="AAPL",
        decision=DecisionAction.BUY,
        reason="approved buy",
        confidence=1.0,
        risk_score=0.2,
        timestamp=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
        supporting_data={
            "validation": {
                "shariah_approval": True,
                "data_availability": True,
                "analysis_completion": True,
                "risk_approval": True,
            }
        },
    )


def _seed_data(core: CoreEngine) -> None:
    session_factory = core.session_factory
    MarketRepository(session_factory).add_candles([_candle(i) for i in range(40)], provider="test")
    ShariahRepository(session_factory).add_records([_compliance()])
    CompanyRepository(session_factory).add_fundamentals([_fundamentals()])


class TestEnvironmentSeparation:
    """Production must never wire an execution broker (AIOS-802, AIOS-603 section 11)."""

    async def test_production_boot_wires_no_broker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        core = await _boot_core(monkeypatch, Environment.PRODUCTION)
        try:
            assert core.is_ready()
            assert core.broker_service is None
            assert core.paper_coordinator is None
            status = core.status()
            assert status["environment"] == "production"
            assert status["components"]["broker"] is False
        finally:
            await core.shutdown()

    async def test_paper_boot_wires_paper_only_broker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_core(monkeypatch, Environment.PAPER)
        try:
            assert core.broker_service is not None
            assert core.broker_service.broker_id == "paper"
            assert core.broker_service.broker.__class__.__name__ == "PaperBroker"
            status = core.status()
            assert status["environment"] == "paper"
            assert status["components"]["broker"] is True
        finally:
            await core.shutdown()


class TestProductionConfigurationReadiness:
    async def test_production_settings_identify_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_core(monkeypatch, Environment.PRODUCTION)
        try:
            assert core.settings.environment is Environment.PRODUCTION
            assert core.settings.debug is False
            assert core.settings.logging.format is LoggingFormat.JSON
            assert core.settings.logging.destination is LoggingDestination.FILE
            assert core.settings.logging.file_backup_count == 5
        finally:
            await core.shutdown()

    def test_production_configuration_contains_no_secrets(self) -> None:
        settings = TomlSettingsLoader(Environment.PRODUCTION).load()
        lowered = {key.lower(): value for key, value in settings.items()}
        for secret_key in ("password", "secret", "api_key", "token"):
            assert secret_key not in lowered


class TestHealthSnapshotOverBootedCore:
    async def test_ready_core_yields_available_snapshot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_core(monkeypatch, Environment.TESTING)
        try:
            snapshot = HealthMonitor().snapshot(core.status())
            assert snapshot.environment == "testing"
            assert snapshot.state == "ready"
            assert snapshot.service_available is True
            assert snapshot.data_available is True
            assert snapshot.broker_connected is False
            assert snapshot.agent_loaded == 7
            assert snapshot.agent_ready == 7
            assert snapshot.engine_loaded == 6
            assert snapshot.engine_ready == 6
            # Phase 7: TESTING environment has 3 mock providers
            assert snapshot.providers_connected == 3
        finally:
            await core.shutdown()

    async def test_paper_broker_reflected_as_connected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_core(monkeypatch, Environment.PAPER)
        try:
            snapshot = HealthMonitor().snapshot(core.status())
            assert snapshot.broker_connected is True
        finally:
            await core.shutdown()

    async def test_shutdown_core_reports_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        core = await _boot_core(monkeypatch, Environment.TESTING)
        await core.shutdown()
        snapshot = HealthMonitor().snapshot(core.status())
        assert snapshot.state == "shutdown"
        assert snapshot.service_available is False


class TestEngineMetricsFeedMonitoring:
    async def test_metrics_aggregate_without_invented_thresholds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_core(monkeypatch, Environment.TESTING)
        try:
            _seed_data(core)
            technical = core.engine_manager.get_by_type(EngineType.TECHNICAL)[0]
            for _ in range(2):
                await core.engine_manager.execute(
                    technical.engine_id,
                    EngineInput(request_id="sys-perf", payload={"symbol": "AAPL"}),
                )
            snapshot = HealthMonitor().snapshot(core.status(), engine_metrics=[technical.metrics()])
            performance = snapshot.performance
            assert performance["engines"] == 1
            assert performance["execution_count"] == 2
            assert performance["failure_count"] == 0
            assert performance["total_duration_seconds"] >= 0
            assert len(performance["engines_detail"]) == 1
            assert performance["engines_detail"][0]["engine_type"] == "technical"
            for invented in ("alert_threshold", "cpu_percent", "memory_bytes"):
                assert invented not in performance
        finally:
            await core.shutdown()


class TestNoLiveBrokerInSource:
    def test_only_paper_broker_is_a_concrete_adapter(self) -> None:
        from aios.brokers import paper as paper_module

        concrete = {
            name
            for name, obj in vars(paper_module).items()
            if isinstance(obj, type) and name.endswith("Broker")
        }
        assert concrete == {"PaperBroker"}

    def test_source_imports_no_live_broker_sdk(self) -> None:
        source_root = _PROJECT_ROOT / "src"
        offenders: list[str] = []
        for path in source_root.rglob("*.py"):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.lstrip()
                if re.match(r"(import|from)\s+alpaca", stripped):
                    offenders.append(f"{path}:{lineno}")
                if re.search(r"\bLiveBroker\b|\blive_broker\b", line):
                    offenders.append(f"{path}:{lineno}")
        assert not offenders, f"live-broker references found: {offenders}"


class TestDecisionOrderTraceability:
    async def test_stored_order_links_to_stored_decision(
        self, monkeypatch: pytest.MonkeyPatch
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
            stored_order = broker_service.get_order(order.order_id)
            stored_decision = DecisionRepository(session_factory).get_latest_decision("AAPL")
            assert stored_order.decision_ref == "AAPL:2026-08-01T12:00:00+00:00"
            assert stored_order.symbol == stored_decision.symbol
            assert stored_order.decision_ref.startswith(stored_decision.symbol)
        finally:
            await core.shutdown()
