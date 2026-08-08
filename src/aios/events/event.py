"""Base event model for the AIOS internal Event Bus (ADR-0005, AIOS-103).

Every event follows the structure defined in AIOS-103:
    - Event ID (UUID, mandatory)
    - Timestamp (UTC)
    - Source
    - Event Type
    - Payload
    - Priority
    - Status
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventPriority(str, Enum):
    """Event priority (AIOS-103)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventStatus(str, Enum):
    """Lifecycle status of an event on the bus (ADR-0005 sections 5.4, 5.5)."""

    CREATED = "created"
    PERSISTED = "persisted"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class Event(BaseModel):
    """Base event model carried by the AIOS Event Bus.

    Attributes:
        event_id: Unique event identifier (UUID). Required by ADR-0005.
        timestamp: Event creation time in UTC.
        source: Component or agent that published the event.
        event_type: Type of the event (e.g. ``MARKET_DATA_UPDATED``).
        payload: Event data, serializable.
        priority: Delivery priority (AIOS-103).
        status: Lifecycle status of the event (ADR-0005).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: EventPriority = EventPriority.MEDIUM
    status: EventStatus = EventStatus.CREATED

    @field_validator("source")
    @classmethod
    def source_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source must not be empty")
        return value.strip()

    @field_validator("event_type")
    @classmethod
    def event_type_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("event_type must not be empty")
        return value.strip()
