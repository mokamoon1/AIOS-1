"""Tests for the Core Engine bootstrap (AIOS-104 section 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.agents.types import AgentState, AgentType
from aios.config import Environment
from aios.core import CoreBootstrapError, CoreEngine, CoreState, CoreStateError
from aios.engines.types import EngineState, EngineType
from aios.errors import ConfigurationError
from aios.events import Event


def _core() -> CoreEngine:
    return CoreEngine(environment=Environment.TESTING)


async def test_start_reaches_ready() -> None:
    core = _core()
    await core.start()
    assert core.is_ready()
    assert core.state is CoreState.READY
    assert core.settings is not None
    assert core.bus is not None
    assert core.session_factory is not None
    assert core.agent_manager is not None
    assert core.engine_manager is not None
    assert core.provider_manager is not None
    await core.shutdown()


async def test_start_loads_full_agent_and_engine_rosters() -> None:
    core = _core()
    await core.start()
    assert [a.agent_type for a in core.agent_manager.list_agents()] == list(AgentType)
    assert [e.engine_type for e in core.engine_manager.list_engines()] == list(EngineType)
    await core.shutdown()


async def test_status_reports_components() -> None:
    core = _core()
    await core.start()
    status = core.status()
    assert status["state"] == "ready"
    assert status["components"]["configuration"] is True
    assert status["components"]["database"] is True
    assert status["components"]["event_bus"] is True
    assert status["components"]["agents"] == {"loaded": 8, "ready": 8}
    assert status["components"]["engines"] == {"loaded": 6, "ready": 6}
    await core.shutdown()


async def test_start_publishes_system_ready_event(monkeypatch) -> None:
    core = _core()
    seen: list[Event] = []
    original = CoreEngine._start_event_bus

    async def capture_start_event_bus(self: CoreEngine) -> None:
        await original(self)

        async def record(event: Event) -> None:
            seen.append(event)

        self.bus.subscribe("SYSTEM_READY", record)  # type: ignore[union-attr]

    monkeypatch.setattr(CoreEngine, "_start_event_bus", capture_start_event_bus)
    await core.start()
    assert len(seen) == 1
    assert seen[0].source == "core.engine"
    await core.shutdown()


async def test_shutdown_tears_down_components() -> None:
    core = _core()
    await core.start()
    agents = core.agent_manager.list_agents()
    engines = core.engine_manager.list_engines()
    await core.shutdown()
    assert core.state is CoreState.SHUTDOWN
    assert all(agent.state is AgentState.SHUTDOWN for agent in agents)
    assert all(engine.state is EngineState.SHUTDOWN for engine in engines)
    assert core.agent_manager.list_agents() == []
    assert core.engine_manager.list_engines() == []


async def test_start_twice_raises() -> None:
    core = _core()
    await core.start()
    with pytest.raises(CoreStateError):
        await core.start()
    await core.shutdown()


async def test_shutdown_before_start_is_noop() -> None:
    core = _core()
    await core.shutdown()
    assert core.state is CoreState.UNINITIALIZED


async def test_missing_configuration_file_fails_and_marks_failed() -> None:
    core = CoreEngine(
        environment=Environment.TESTING,
        config_dir=Path("does/not/exist"),
    )
    with pytest.raises(CoreBootstrapError):
        await core.start()
    assert core.state is CoreState.FAILED
    assert not core.is_ready()


async def test_start_failure_rolls_back_loaded_components(monkeypatch) -> None:
    core = _core()

    async def boom() -> None:
        raise RuntimeError("provider failure")

    monkeypatch.setattr(core, "_start_providers", boom)
    with pytest.raises(CoreBootstrapError):
        await core.start()
    assert core.state is CoreState.FAILED
    assert core.agent_manager.list_agents() == []
    assert core.engine_manager.list_engines() == []


async def test_configuration_error_is_wrapped_and_cause_preserved() -> None:
    core = CoreEngine(
        environment=Environment.TESTING,
        config_dir=Path("does/not/exist"),
    )
    with pytest.raises(CoreBootstrapError) as excinfo:
        await core.start()
    assert isinstance(excinfo.value.__cause__, ConfigurationError)
