"""Integration tests for the Core Engine bootstrap (AIOS-104 section 4).

These tests boot the full platform — configuration, logging, database,
Event Bus, Agent Manager, Engine Manager, and providers — and verify the
documented startup sequence, health/readiness reporting, clean shutdown,
rollback on failure, and end-to-end behavior of the Event Bus, Agent
Manager, Engine Manager, and error handling (AIOS-104 sections 4, 5, and 7).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import aios.core.engine as core_module
import aios.database.models  # noqa: F401  (register ORM models on Base.metadata)
from aios.agents.messages import AgentContext
from aios.agents.types import AgentState, AgentType
from aios.config import Environment
from aios.config.settings import LoggingDestination
from aios.core import CoreBootstrapError, CoreEngine, CoreState
from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.database.base import Base
from aios.database.repositories import CompanyRepository, MarketRepository, ShariahRepository
from aios.engines.messages import EngineInput
from aios.engines.types import EngineState, EngineType
from aios.errors import EngineError
from aios.events import Event

pytestmark = pytest.mark.integration

_START_STAGES = [
    "_start_configuration",
    "_start_logging",
    "_start_database",
    "_start_event_bus",
    "_start_agents",
    "_start_engines",
    "_start_broker",
    "_start_providers",
]


class EventRecorder:
    """Collects events of the requested types published on the bootstrap bus."""

    def __init__(self, event_types: list[str]) -> None:
        self.events: dict[str, list[Event]] = defaultdict(list)
        self._wanted = set(event_types)

    async def handler(self, event: Event) -> None:
        if event.event_type in self._wanted:
            self.events[event.event_type].append(event)


async def _boot(
    monkeypatch: pytest.MonkeyPatch, *event_types: str
) -> tuple[CoreEngine, EventRecorder]:
    """Start a full Core Engine and return it with an event recorder attached."""
    core = CoreEngine(environment=Environment.TESTING)
    wanted = {"SYSTEM_READY", "SYSTEM_SHUTDOWN", *event_types}
    recorder = EventRecorder(list(wanted))
    original = CoreEngine._start_event_bus

    async def capture_start_event_bus(self: CoreEngine) -> None:
        await original(self)
        self.bus.subscribe("SYSTEM_READY", recorder.handler)
        self.bus.subscribe("SYSTEM_SHUTDOWN", recorder.handler)
        for event_type in event_types:
            if event_type not in {"SYSTEM_READY", "SYSTEM_SHUTDOWN"}:
                self.bus.subscribe(event_type, recorder.handler)

    monkeypatch.setattr(CoreEngine, "_start_event_bus", capture_start_event_bus)
    await core.start()
    return core, recorder


def _sqlite_engine():
    """In-memory SQLite engine with the full AIOS schema (ADR-0001)."""
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


def _candle(index: int) -> Candle:
    """An uptrending daily candle for ``AAPL``."""
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
    """A compliant Shariah record for ``AAPL``."""
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
    """Fundamental figures for ``AAPL``."""
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


def _seed_data(core: CoreEngine) -> None:
    """Seed market, Shariah, and fundamental data for ``AAPL``."""
    session_factory = core.session_factory
    MarketRepository(session_factory).add_candles([_candle(i) for i in range(40)], provider="test")
    ShariahRepository(session_factory).add_records([_compliance()])
    CompanyRepository(session_factory).add_fundamentals([_fundamentals()])


async def _boot_with_data(
    monkeypatch: pytest.MonkeyPatch, *event_types: str
) -> tuple[CoreEngine, EventRecorder]:
    """Boot a Core Engine against an in-memory SQLite database with seed data.

    Analysis engines read through the DataService facade built over the
    startup session factory, so the database must be reachable and seeded
    before engines execute (AIOS-605 section 13).
    """
    monkeypatch.setattr(core_module, "create_db_engine", lambda url, **kwargs: _sqlite_engine())
    core, recorder = await _boot(monkeypatch, *event_types)
    _seed_data(core)
    return core, recorder


async def test_startup_runs_the_documented_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    core = CoreEngine(environment=Environment.TESTING)
    order: list[str] = []
    for name in _START_STAGES:
        original = getattr(CoreEngine, name)

        async def wrap(self: CoreEngine, _name: str = name, _original: object = original) -> None:
            order.append(_name)
            await _original(self)

        monkeypatch.setattr(CoreEngine, name, wrap)
    await core.start()
    assert order == _START_STAGES
    await core.shutdown()


async def test_successful_startup_brings_all_components_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, recorder = await _boot(monkeypatch, "SYSTEM_READY")
    assert core.is_ready()
    assert core.state is CoreState.READY
    assert core.settings is not None
    assert core.session_factory is not None
    assert [a.agent_type for a in core.agent_manager.list_agents()] == list(AgentType)
    assert [e.engine_type for e in core.engine_manager.list_engines()] == list(EngineType)
    assert len(recorder.events["SYSTEM_READY"]) == 1
    await core.shutdown()


async def test_health_and_readiness_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    core, _ = await _boot(monkeypatch)
    status = core.status()
    assert status["state"] == "ready"
    for component in ("configuration", "logging", "database", "event_bus"):
        assert status["components"][component] is True
    assert status["components"]["agents"] == {"loaded": 7, "ready": 7}
    assert status["components"]["engines"] == {"loaded": 6, "ready": 6}
    await core.shutdown()


async def test_not_ready_before_start() -> None:
    core = CoreEngine(environment=Environment.TESTING)
    assert not core.is_ready()
    assert core.status()["state"] == "uninitialized"


async def test_startup_failure_marks_failed_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = CoreEngine(environment=Environment.TESTING)

    async def boom(self: CoreEngine) -> None:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(CoreEngine, "_start_providers", boom)
    with pytest.raises(CoreBootstrapError) as excinfo:
        await core.start()
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert core.state is CoreState.FAILED
    assert not core.is_ready()
    assert core.agent_manager.list_agents() == []
    assert core.engine_manager.list_engines() == []


async def test_startup_configuration_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = CoreEngine(environment=Environment.TESTING)

    async def boom(self: CoreEngine) -> None:
        raise RuntimeError("configuration unavailable")

    monkeypatch.setattr(CoreEngine, "_start_configuration", boom)
    with pytest.raises(CoreBootstrapError):
        await core.start()
    assert core.state is CoreState.FAILED
    assert core.settings is None


async def test_shutdown_is_clean_and_publishes_shutdown_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, recorder = await _boot(monkeypatch, "SYSTEM_SHUTDOWN")
    agents = core.agent_manager.list_agents()
    engines = core.engine_manager.list_engines()
    await core.shutdown()
    assert core.state is CoreState.SHUTDOWN
    assert all(agent.state is AgentState.SHUTDOWN for agent in agents)
    assert all(engine.state is EngineState.SHUTDOWN for engine in engines)
    assert core.agent_manager.list_agents() == []
    assert core.engine_manager.list_engines() == []
    assert len(recorder.events["SYSTEM_SHUTDOWN"]) == 1


async def test_agent_manager_executes_bootstrap_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, _ = await _boot(monkeypatch)
    context = AgentContext(request_id="req-agent", payload={"symbol": "AAPL"})
    result = await core.agent_manager.execute_by_type(AgentType.CIO, context)
    assert result.agent_type is AgentType.CIO
    assert result.request_id == "req-agent"
    assert result.output["received"] is True
    await core.shutdown()


async def test_engine_manager_executes_bootstrap_engines_and_publishes_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, recorder = await _boot_with_data(monkeypatch, "ENGINE_RESULT")
    engine_input = EngineInput(request_id="req-engine", payload={"symbol": "AAPL"})
    result = await core.engine_manager.execute_by_type(EngineType.TECHNICAL, engine_input)
    assert result.engine_type is EngineType.TECHNICAL
    assert result.request_id == "req-engine"
    assert result.processing_duration >= 0
    assert result.output["symbol"] == "AAPL"
    assert len(recorder.events["ENGINE_RESULT"]) == 1
    await core.shutdown()


async def test_engine_execution_order_obeys_declared_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, _ = await _boot(monkeypatch)
    order = core.engine_manager.resolve_execution_order([EngineType.DECISION])
    assert order.index(EngineType.TECHNICAL) < order.index(EngineType.SIGNAL)
    for dependency in (EngineType.MARKET, EngineType.FUNDAMENTAL, EngineType.RISK):
        assert dependency in order
        assert order.index(dependency) < order.index(EngineType.DECISION)
    assert order[-1] is EngineType.DECISION
    await core.shutdown()


async def test_configuration_loaded_from_testing_toml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, _ = await _boot(monkeypatch)
    assert core.settings.app_name == "aios"
    assert core.settings.database.name == "aios_testing"
    assert core.settings.logging.level == "INFO"
    assert core.settings.logging.destination is LoggingDestination.CONSOLE
    await core.shutdown()


async def test_logging_is_configured_for_testing_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, _ = await _boot(monkeypatch)
    aios_logger = logging.getLogger("aios")
    assert aios_logger.level == logging.INFO
    assert len(aios_logger.handlers) == 1
    assert logging.getLogger("aios.audit").propagate is False
    await core.shutdown()


async def test_engine_failure_publishes_error_and_quarantines_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core, recorder = await _boot_with_data(monkeypatch, "ERROR")
    market = core.engine_manager.get_by_type(EngineType.MARKET)[0]

    async def boom(engine_input: EngineInput, data: dict) -> None:
        raise RuntimeError("analysis unavailable")

    monkeypatch.setattr(market, "_analyze", boom)
    with pytest.raises(EngineError):
        await core.engine_manager.execute(
            market.engine_id, EngineInput(request_id="req-err", payload={"symbol": "AAPL"})
        )
    assert market.state is EngineState.FAILED
    assert recorder.events["ERROR"][0].payload["error_type"] == "RuntimeError"
    assert recorder.events["ERROR"][0].payload["component"] == "Market Engine"
    await core.shutdown()
