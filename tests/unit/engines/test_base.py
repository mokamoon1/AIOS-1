"""Tests for the Engine base class lifecycle (AIOS-605 sections 4, 5, 12, 15, 16)."""

from __future__ import annotations

import logging
from typing import ClassVar

import pytest

from aios.engines.base import Engine
from aios.engines.exceptions import EngineStateError, EngineValidationError
from aios.engines.messages import EngineInput, EngineOutput
from aios.engines.types import EngineState, EngineType
from aios.errors import EngineError
from aios.events import Event, InMemoryEventBus


class _EchoEngine(Engine):
    """Test engine that returns a fixed result."""

    engine_type: ClassVar[EngineType] = EngineType.MARKET
    name: ClassVar[str] = "Echo Engine"

    async def _load_data(self, engine_input: EngineInput) -> dict:
        return {"loaded": engine_input.payload}

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output={"echo": data["loaded"]},
            explanation="echoed",
            confidence=0.5,
        )


class _FailingEngine(Engine):
    engine_type: ClassVar[EngineType] = EngineType.RISK
    name: ClassVar[str] = "Failing Engine"

    async def _load_data(self, engine_input: EngineInput) -> dict:
        return {}

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        raise RuntimeError("boom")


class _EmptyOutputEngine(Engine):
    engine_type: ClassVar[EngineType] = EngineType.FUNDAMENTAL
    name: ClassVar[str] = "Empty Output Engine"

    async def _load_data(self, engine_input: EngineInput) -> dict:
        return {}

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output={},
            confidence=0.5,
        )


class _RejectingInputEngine(Engine):
    engine_type: ClassVar[EngineType] = EngineType.TECHNICAL
    name: ClassVar[str] = "Rejecting Input Engine"

    async def _load_data(self, engine_input: EngineInput) -> dict:
        return {}

    def validate_input(self, engine_input: EngineInput) -> bool:
        return False

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output={"echo": True},
            confidence=0.5,
        )


def _engine_input() -> EngineInput:
    return EngineInput(request_id="req-1", payload={"symbol": "AAPL"})


async def test_initialization_transitions_to_initialized() -> None:
    engine = _EchoEngine()
    assert engine.state is EngineState.UNINITIALIZED
    engine.initialize()
    assert engine.state is EngineState.INITIALIZED


def test_initialize_twice_raises() -> None:
    engine = _EchoEngine()
    engine.initialize()
    with pytest.raises(EngineStateError):
        engine.initialize()


async def test_execute_happy_path_returns_result() -> None:
    engine = _EchoEngine()
    engine.initialize()
    result = await engine.execute(_engine_input())
    assert result.output == {"echo": {"symbol": "AAPL"}}
    assert result.confidence == 0.5
    assert result.engine_id == engine.engine_id


async def test_execute_returns_to_idle() -> None:
    engine = _EchoEngine()
    engine.initialize()
    await engine.execute(_engine_input())
    assert engine.state is EngineState.IDLE


async def test_execute_publishes_result_event() -> None:
    bus = InMemoryEventBus()
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    bus.subscribe("ENGINE_RESULT", capture)
    engine = _EchoEngine(bus=bus)
    engine.initialize()

    await engine.execute(_engine_input())

    assert len(received) == 1
    assert received[0].event_type == "ENGINE_RESULT"
    assert received[0].payload["result"]["engine_type"] == "market"
    assert received[0].payload["result"]["request_id"] == "req-1"


async def test_execute_without_bus_does_not_publish() -> None:
    engine = _EchoEngine()
    engine.initialize()
    result = await engine.execute(_engine_input())
    assert result.request_id == "req-1"


async def test_execute_before_initialize_raises() -> None:
    engine = _EchoEngine()
    with pytest.raises(EngineStateError):
        await engine.execute(_engine_input())


async def test_failing_engine_is_quarantined_and_notified(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = InMemoryEventBus()
    errors: list[Event] = []

    async def capture(event: Event) -> None:
        errors.append(event)

    bus.subscribe("ERROR", capture)
    engine = _FailingEngine(bus=bus)
    engine.initialize()

    with caplog.at_level(logging.ERROR), pytest.raises(EngineError):
        await engine.execute(_engine_input())

    assert engine.state is EngineState.FAILED
    assert len(errors) == 1
    assert errors[0].event_type == "ERROR"
    assert "RuntimeError" in errors[0].payload["error_type"]
    assert errors[0].payload["details"]["engine_id"] == engine.engine_id


async def test_validation_rejects_empty_output() -> None:
    engine = _EmptyOutputEngine()
    engine.initialize()
    with pytest.raises(EngineValidationError):
        await engine.execute(_engine_input())


async def test_validation_rejects_invalid_input() -> None:
    engine = _RejectingInputEngine()
    engine.initialize()
    with pytest.raises(EngineValidationError):
        await engine.execute(_engine_input())


async def test_reset_returns_failed_engine_to_initialized() -> None:
    engine = _FailingEngine()
    engine.initialize()
    with pytest.raises(EngineError):
        await engine.execute(_engine_input())
    assert engine.state is EngineState.FAILED
    engine.reset()
    assert engine.state is EngineState.INITIALIZED


async def test_reset_from_idle() -> None:
    engine = _EchoEngine()
    engine.initialize()
    await engine.execute(_engine_input())
    engine.reset()
    assert engine.state is EngineState.INITIALIZED


async def test_shutdown_transitions() -> None:
    engine = _EchoEngine()
    engine.initialize()
    engine.shutdown()
    assert engine.state is EngineState.SHUTDOWN
    with pytest.raises(EngineStateError):
        engine.shutdown()


async def test_execute_after_shutdown_raises() -> None:
    engine = _EchoEngine()
    engine.initialize()
    engine.shutdown()
    with pytest.raises(EngineStateError):
        await engine.execute(_engine_input())


async def test_explain_returns_explanation() -> None:
    engine = _EchoEngine()
    engine.initialize()
    result = await engine.execute(_engine_input())
    assert engine.explain(result) == "echoed"


async def test_metrics_track_execution_and_duration() -> None:
    engine = _EchoEngine()
    engine.initialize()
    await engine.execute(_engine_input())
    await engine.execute(_engine_input())
    metrics = engine.metrics()
    assert metrics["engine_id"] == engine.engine_id
    assert metrics["engine_type"] == "market"
    assert metrics["execution_count"] == 2
    assert metrics["failure_count"] == 0
    assert metrics["failure_rate"] == 0.0
    assert metrics["total_duration_seconds"] > 0.0
    assert metrics["average_duration_seconds"] > 0.0
    assert metrics["confidence_distribution"] == [0.5, 0.5]


async def test_metrics_track_failure_rate() -> None:
    engine = _FailingEngine()
    engine.initialize()
    with pytest.raises(EngineError):
        await engine.execute(_engine_input())
    metrics = engine.metrics()
    assert metrics["execution_count"] == 1
    assert metrics["failure_count"] == 1
    assert metrics["failure_rate"] == 1.0


def test_metrics_empty_before_execution() -> None:
    engine = _EchoEngine()
    metrics = engine.metrics()
    assert metrics["execution_count"] == 0
    assert metrics["failure_rate"] == 0.0
    assert metrics["average_duration_seconds"] == 0.0
