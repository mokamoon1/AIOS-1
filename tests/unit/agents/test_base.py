"""Tests for the Agent base class lifecycle (AIOS-604 sections 4, 5, 6, 14, 15)."""

from __future__ import annotations

import logging
from typing import ClassVar

import pytest

from aios.agents.base import Agent
from aios.agents.exceptions import AgentStateError
from aios.agents.messages import AgentContext, AgentResult, MessageStatus
from aios.agents.types import AgentState, AgentType
from aios.errors import AgentError
from aios.events import Event, InMemoryEventBus


class _EchoAgent(Agent):
    """Test agent that returns a fixed result."""

    agent_type: ClassVar[AgentType] = AgentType.MARKET
    name: ClassVar[str] = "Echo Agent"

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output={"echo": context.payload},
            explanation="echoed",
            confidence=0.5,
        )


class _FailingAgent(Agent):
    agent_type: ClassVar[AgentType] = AgentType.RISK
    name: ClassVar[str] = "Failing Agent"

    async def _process(self, context: AgentContext) -> AgentResult:
        raise RuntimeError("boom")


class _EmptyOutputAgent(Agent):
    agent_type: ClassVar[AgentType] = AgentType.FUNDAMENTAL
    name: ClassVar[str] = "Empty Output Agent"

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output={},
            confidence=0.5,
        )


def _context() -> AgentContext:
    return AgentContext(request_id="req-1", payload={"symbol": "AAPL"})


async def test_initialization_transitions_to_initialized() -> None:
    agent = _EchoAgent()
    assert agent.state is AgentState.UNINITIALIZED
    agent.initialize()
    assert agent.state is AgentState.INITIALIZED


def test_initialize_twice_raises() -> None:
    agent = _EchoAgent()
    agent.initialize()
    with pytest.raises(AgentStateError):
        agent.initialize()


async def test_execute_happy_path_returns_result() -> None:
    agent = _EchoAgent()
    agent.initialize()
    result = await agent.execute(_context())
    assert result.output == {"echo": {"symbol": "AAPL"}}
    assert result.confidence == 0.5


async def test_execute_returns_to_idle() -> None:
    agent = _EchoAgent()
    agent.initialize()
    await agent.execute(_context())
    assert agent.state is AgentState.IDLE


async def test_execute_publishes_result_event() -> None:
    bus = InMemoryEventBus()
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    bus.subscribe("AGENT_RESULT", capture)
    agent = _EchoAgent(bus=bus)
    agent.initialize()

    await agent.execute(_context())

    assert len(received) == 1
    assert received[0].event_type == "AGENT_RESULT"
    assert received[0].payload["result"]["agent_type"] == "market"


async def test_execute_without_bus_does_not_publish() -> None:
    agent = _EchoAgent()
    agent.initialize()
    result = await agent.execute(_context())
    assert result.request_id == "req-1"


async def test_execute_before_initialize_raises() -> None:
    agent = _EchoAgent()
    with pytest.raises(AgentStateError):
        await agent.execute(_context())


async def test_failing_agent_is_quarantined_and_notified(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = InMemoryEventBus()
    errors: list[Event] = []

    async def capture(event: Event) -> None:
        errors.append(event)

    bus.subscribe("ERROR", capture)
    agent = _FailingAgent(bus=bus)
    agent.initialize()

    with caplog.at_level(logging.ERROR), pytest.raises(AgentError):
        await agent.execute(_context())

    assert agent.state is AgentState.FAILED
    assert len(errors) == 1
    assert errors[0].event_type == "ERROR"
    assert "RuntimeError" in errors[0].payload["error_type"]


async def test_validation_rejects_empty_output() -> None:
    agent = _EmptyOutputAgent()
    agent.initialize()
    with pytest.raises(AgentError):
        await agent.execute(_context())


async def test_reset_returns_failed_agent_to_initialized() -> None:
    agent = _FailingAgent()
    agent.initialize()
    with pytest.raises(AgentError):
        await agent.execute(_context())
    assert agent.state is AgentState.FAILED
    agent.reset()
    assert agent.state is AgentState.INITIALIZED


async def test_reset_from_idle() -> None:
    agent = _EchoAgent()
    agent.initialize()
    await agent.execute(_context())
    agent.reset()
    assert agent.state is AgentState.INITIALIZED


async def test_shutdown_transitions() -> None:
    agent = _EchoAgent()
    agent.initialize()
    agent.shutdown()
    assert agent.state is AgentState.SHUTDOWN
    with pytest.raises(AgentStateError):
        agent.shutdown()


async def test_execute_after_shutdown_raises() -> None:
    agent = _EchoAgent()
    agent.initialize()
    agent.shutdown()
    with pytest.raises(AgentStateError):
        await agent.execute(_context())


async def test_explain_returns_explanation() -> None:
    agent = _EchoAgent()
    agent.initialize()
    result = await agent.execute(_context())
    assert agent.explain(result) == "echoed"


async def test_send_message_publishes_structured_message() -> None:
    bus = InMemoryEventBus()
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    bus.subscribe("AGENT_MESSAGE", capture)
    agent = _EchoAgent(bus=bus)
    agent.initialize()

    message = await agent.send_message(
        receiver=AgentType.CIO,
        request_id="req-2",
        payload={"signal": "buy"},
        confidence=0.7,
    )

    assert message.sender is AgentType.MARKET
    assert message.receiver is AgentType.CIO
    assert message.status is MessageStatus.COMPLETED
    assert len(received) == 1
    assert received[0].event_type == "AGENT_MESSAGE"
    assert received[0].payload["sender"] == "market"
    assert received[0].payload["receiver"] == "cio"


async def test_send_message_without_bus_raises() -> None:
    agent = _EchoAgent()
    agent.initialize()
    with pytest.raises(AgentError):
        await agent.send_message(receiver=AgentType.CIO, request_id="req-2")
