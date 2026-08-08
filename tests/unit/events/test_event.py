"""Tests for the base Event model (AIOS-103, ADR-0005)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from aios.events import Event, EventPriority, EventStatus


def test_event_creation() -> None:
    event = Event(source="market", event_type="MARKET_DATA_UPDATED")

    assert isinstance(event.event_id, UUID)
    assert event.event_id.version == 4
    assert event.timestamp.tzinfo is timezone.utc
    assert event.source == "market"
    assert event.event_type == "MARKET_DATA_UPDATED"
    assert event.payload == {}
    assert event.priority is EventPriority.MEDIUM
    assert event.status is EventStatus.CREATED


def test_event_creation_with_explicit_fields() -> None:
    event = Event(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        source="decision_engine",
        event_type="SIGNAL_GENERATED",
        payload={"symbol": "AAPL", "confidence": 0.9},
        priority=EventPriority.HIGH,
    )

    assert event.event_id == UUID("12345678-1234-5678-1234-567812345678")
    assert event.timestamp == datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert event.source == "decision_engine"
    assert event.event_type == "SIGNAL_GENERATED"
    assert event.payload == {"symbol": "AAPL", "confidence": 0.9}
    assert event.priority is EventPriority.HIGH


def test_event_generates_distinct_ids() -> None:
    first = Event(source="a", event_type="TYPE_A")
    second = Event(source="a", event_type="TYPE_A")

    assert first.event_id != second.event_id


def test_event_requires_source() -> None:
    with pytest.raises(ValidationError):
        Event(source="", event_type="TYPE_A")


def test_event_requires_event_type() -> None:
    with pytest.raises(ValidationError):
        Event(source="a", event_type="   ")


def test_event_strips_whitespace_source_and_type() -> None:
    event = Event(source="  market  ", event_type="  PRICE_CHANGED  ")

    assert event.source == "market"
    assert event.event_type == "PRICE_CHANGED"


def test_event_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Event(source="a", event_type="TYPE_A", unknown_field=1)  # type: ignore[call-arg]


def test_event_is_immutable() -> None:
    event = Event(source="a", event_type="TYPE_A")

    with pytest.raises(ValidationError):
        event.source = "b"  # type: ignore[misc]
