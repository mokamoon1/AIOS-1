"""Tests for the Engine Manager registry and execution order (AIOS-605 section 3)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.engines.exceptions import (
    EngineDependencyError,
    EngineNotFoundError,
    EngineRegistrationError,
)
from aios.engines.manager import EngineManager
from aios.engines.messages import EngineInput
from aios.engines.roster import (
    MarketEngine,
    SignalEngine,
    TechnicalEngine,
    create_engine,
)
from aios.engines.types import EngineState, EngineType


def _engine_input() -> EngineInput:
    return EngineInput(request_id="req-1", payload={"symbol": "AAPL"})


def _candle(index: int, close: float) -> Candle:
    return Candle(
        timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc),
        symbol="AAPL",
        timeframe=Timeframe.ONE_DAY,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1000.0,
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
        equity=1200.0,
        report_date=date(2026, 6, 30),
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


class _FakeDataAccess:
    def get_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000) -> list[Candle]:
        return [_candle(i, 10.0 + i * 0.5) for i in range(40)]

    def get_fundamentals(self, symbol, *, report_date=None) -> CompanyFundamentals:
        return _fundamentals()

    def get_compliance_status(self, symbol, *, as_of=None) -> ShariahCompliance:
        return _compliance()

    def list_positions(self, *, status=None) -> list:
        return []

    def store_decisions(self, decisions: list) -> int:
        return len(decisions)


def _make_manager() -> EngineManager:
    manager = EngineManager()
    for engine_type in EngineType:
        manager.register(create_engine(engine_type, data_access=_FakeDataAccess()))
    return manager


def test_register_and_get() -> None:
    manager = EngineManager()
    engine = create_engine(EngineType.MARKET)
    manager.register(engine)
    assert manager.get(engine.engine_id) is engine
    assert engine.state is EngineState.INITIALIZED


def test_register_duplicate_raises() -> None:
    manager = EngineManager()
    engine = create_engine(EngineType.MARKET)
    manager.register(engine)
    with pytest.raises(EngineRegistrationError):
        manager.register(engine)


def test_register_initialized_engine_raises() -> None:
    manager = EngineManager()
    engine = create_engine(EngineType.MARKET)
    engine.initialize()
    with pytest.raises(EngineRegistrationError):
        manager.register(engine)


def test_get_missing_raises() -> None:
    manager = EngineManager()
    with pytest.raises(EngineNotFoundError):
        manager.get("missing")


def test_get_by_type() -> None:
    manager = _make_manager()
    engines = manager.get_by_type(EngineType.TECHNICAL)
    assert len(engines) == 1
    assert isinstance(engines[0], TechnicalEngine)


def test_get_by_type_empty() -> None:
    manager = EngineManager()
    assert manager.get_by_type(EngineType.RISK) == []


def test_list_engines_in_registration_order() -> None:
    manager = _make_manager()
    assert [e.engine_type for e in manager.list_engines()] == list(EngineType)


def test_status_map() -> None:
    manager = _make_manager()
    status = manager.status()
    assert set(status.values()) == {EngineState.INITIALIZED}
    assert len(status) == len(EngineType)


def test_unregister_shuts_down_and_removes() -> None:
    manager = _make_manager()
    engine = manager.get_by_type(EngineType.RISK)[0]
    manager.unregister(engine.engine_id)
    assert engine.state is EngineState.SHUTDOWN
    with pytest.raises(EngineNotFoundError):
        manager.get(engine.engine_id)


async def test_execute_by_id() -> None:
    manager = _make_manager()
    engine = manager.get_by_type(EngineType.MARKET)[0]
    result = await manager.execute(engine.engine_id, _engine_input())
    assert result.engine_id == engine.engine_id
    assert result.output["symbol"] == "AAPL"


async def test_execute_by_type() -> None:
    manager = _make_manager()
    result = await manager.execute_by_type(EngineType.TECHNICAL, _engine_input())
    assert result.engine_type is EngineType.TECHNICAL


async def test_execute_by_type_missing_raises() -> None:
    manager = EngineManager()
    with pytest.raises(EngineNotFoundError):
        await manager.execute_by_type(EngineType.SIGNAL, _engine_input())


def test_resolve_execution_order_respects_dependencies() -> None:
    manager = _make_manager()
    order = manager.resolve_execution_order(
        [EngineType.DECISION, EngineType.TECHNICAL, EngineType.SIGNAL, EngineType.MARKET]
    )
    assert order.index(EngineType.TECHNICAL) < order.index(EngineType.SIGNAL)
    assert order.index(EngineType.SIGNAL) < order.index(EngineType.DECISION)
    assert order.index(EngineType.MARKET) < order.index(EngineType.DECISION)
    # The Decision Engine's declared dependencies are expanded into the order.
    assert set(order) == set(EngineType)


def test_resolve_execution_order_is_deterministic() -> None:
    manager = _make_manager()
    first = manager.resolve_execution_order(list(EngineType))
    second = manager.resolve_execution_order(list(EngineType))
    assert first == second


def test_resolve_execution_order_without_dependencies() -> None:
    manager = _make_manager()
    order = manager.resolve_execution_order([EngineType.FUNDAMENTAL, EngineType.RISK])
    assert set(order) == {EngineType.FUNDAMENTAL, EngineType.RISK}


def test_resolve_execution_order_missing_engine_raises() -> None:
    manager = EngineManager()
    manager.register(create_engine(EngineType.MARKET))
    with pytest.raises(EngineNotFoundError):
        manager.resolve_execution_order([EngineType.MARKET, EngineType.SIGNAL])


def test_resolve_execution_order_cycle_raises() -> None:
    class _A(MarketEngine):
        engine_type = EngineType.MARKET
        dependencies = frozenset({EngineType.SIGNAL})

    class _S(SignalEngine):
        engine_type = EngineType.SIGNAL
        dependencies = frozenset({EngineType.MARKET})

    manager = EngineManager()
    manager.register(_A())
    manager.register(_S())
    with pytest.raises(EngineDependencyError):
        manager.resolve_execution_order([EngineType.MARKET, EngineType.SIGNAL])


def test_decision_engine_requires_all_dependencies_executed_first() -> None:
    manager = _make_manager()
    order = manager.resolve_execution_order([EngineType.DECISION])
    # Decision depends on all five analysis engines; they must all be present.
    assert set(order) == {
        EngineType.MARKET,
        EngineType.TECHNICAL,
        EngineType.FUNDAMENTAL,
        EngineType.RISK,
        EngineType.SIGNAL,
        EngineType.DECISION,
    }
    assert order[-1] is EngineType.DECISION


def test_empty_resolve_execution_order() -> None:
    manager = EngineManager()
    assert manager.resolve_execution_order([]) == []


async def test_full_pipeline_executes_all_engines() -> None:
    manager = _make_manager()
    order = manager.resolve_execution_order(list(EngineType))
    results = {}
    for engine_type in order:
        engine = manager.get_by_type(engine_type)[0]
        results[engine_type] = await manager.execute(engine.engine_id, _engine_input())
    assert set(results) == set(EngineType)
    for result in results.values():
        assert result.output
        assert result.request_id == "req-1"


async def test_run_pipeline_feeds_prior_outputs_in_dependency_order() -> None:
    manager = _make_manager()
    input_with_limits = EngineInput(
        request_id="req-pipeline",
        payload={"symbol": "AAPL", "max_position_percentage": 50},
    )
    results = await manager.run_pipeline([EngineType.DECISION], input_with_limits)
    assert set(results) == {
        EngineType.MARKET,
        EngineType.TECHNICAL,
        EngineType.FUNDAMENTAL,
        EngineType.RISK,
        EngineType.SIGNAL,
        EngineType.DECISION,
    }
    risk = results[EngineType.RISK]
    assert risk.output["approval_status"] == "approved"
    decision = results[EngineType.DECISION]
    assert decision.output["validation"]["status"] == "VALID"
    # Decision Engine now produces directional decision (BUY/SELL/HOLD) when all gates pass
    assert decision.output["decision"] in {"buy", "sell", "hold"}
    assert decision.output["decision_score"] is not None
    assert decision.output["persisted"] is True
    assert decision.output["risk_level"] == "acceptable"


async def test_run_pipeline_risk_not_evaluated_passes_gate() -> None:
    """Risk gate only blocks on 'blocked'; 'not_evaluated' passes."""
    manager = _make_manager()
    results = await manager.run_pipeline([EngineType.DECISION], _engine_input())
    decision = results[EngineType.DECISION]
    # Risk not_evaluated -> not blocked -> gate passes
    # All hard constraints pass -> weighted scoring produces directional decision
    assert decision.output["validation"]["status"] == "VALID"
    assert decision.output["decision"] in {"buy", "sell", "hold"}
    assert decision.output["decision_score"] is not None
    assert decision.output["risk_level"] == "not_evaluated"


async def test_run_pipeline_rejects_missing_risk_when_limited_set() -> None:
    manager = _make_manager()
    results = await manager.run_pipeline(
        [EngineType.MARKET, EngineType.TECHNICAL, EngineType.FUNDAMENTAL],
        _engine_input(),
    )
    assert EngineType.DECISION not in results
    assert set(results) == {
        EngineType.MARKET,
        EngineType.TECHNICAL,
        EngineType.FUNDAMENTAL,
    }
