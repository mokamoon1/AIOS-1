"""Standard agent message and result models (AIOS-604 sections 5 and 14).

Agents receive standardized context, produce structured results that
include reasoning and confidence, and communicate through structured
messages. Messages include sender, receiver, timestamp, request identifier,
payload, confidence, and status per AIOS-604 section 14.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aios.agents.types import AgentType


class MessageStatus(str, Enum):
    """Status of an agent message (AIOS-604 section 14)."""

    REQUESTED = "requested"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentContext(BaseModel):
    """Standardized input received by an agent (AIOS-604 section 4).

    Receive Context is the second stage of the agent lifecycle; the
    context carries the request identifier and structured payload the agent
    processes.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request_id must not be empty")
        return value.strip()


class AgentResult(BaseModel):
    """Structured output produced by an agent (AIOS-604 sections 5 and 10).

    Every agent must explain its reasoning and report confidence. Outputs
    are validated before publication (Validate Output stage).
    """

    model_config = ConfigDict(extra="forbid")

    agent_type: AgentType
    request_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AgentMessage(BaseModel):
    """Structured message exchanged between agents (AIOS-604 section 14).

    Agents communicate through the Event Bus (ADR-0005). This model defines
    the message fields mandated by AIOS-604 section 14: sender, receiver,
    timestamp, request identifier, payload, confidence, and status.
    """

    model_config = ConfigDict(extra="forbid")

    message_id: UUID = Field(default_factory=uuid4)
    sender: AgentType
    receiver: AgentType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: MessageStatus = MessageStatus.COMPLETED

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request_id must not be empty")
        return value.strip()
