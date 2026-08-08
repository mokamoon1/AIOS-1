"""Tests for agent messages, context, and results (AIOS-604 sections 4, 5, 14)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aios.agents.messages import (
    AgentContext,
    AgentMessage,
    AgentResult,
    MessageStatus,
)
from aios.agents.types import AgentType


class TestAgentContext:
    def test_requires_request_id(self) -> None:
        with pytest.raises(ValidationError):
            AgentContext(request_id="")

    def test_payload_defaults_to_empty(self) -> None:
        context = AgentContext(request_id="req-1")
        assert context.payload == {}

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            AgentContext(request_id="req-1", unknown=1)  # type: ignore[call-arg]


class TestAgentResult:
    def test_defaults(self) -> None:
        result = AgentResult(agent_type=AgentType.MARKET, request_id="req-1")
        assert result.output == {}
        assert result.confidence == 0.0

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            AgentResult(agent_type=AgentType.MARKET, request_id="req-1", confidence=1.5)
        with pytest.raises(ValidationError):
            AgentResult(agent_type=AgentType.MARKET, request_id="req-1", confidence=-0.1)


class TestAgentMessage:
    def test_message_has_required_fields(self) -> None:
        message = AgentMessage(
            sender=AgentType.MARKET,
            receiver=AgentType.CIO,
            request_id="req-1",
            payload={"bias": "bullish"},
            confidence=0.8,
        )
        assert message.sender is AgentType.MARKET
        assert message.receiver is AgentType.CIO
        assert message.request_id == "req-1"
        assert message.status is MessageStatus.COMPLETED
        assert message.confidence == 0.8

    def test_request_id_must_not_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            AgentMessage(
                sender=AgentType.MARKET,
                receiver=AgentType.CIO,
                request_id="",
            )
