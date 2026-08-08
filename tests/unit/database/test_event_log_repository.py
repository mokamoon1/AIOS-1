"""EventLogRepository tests (ADR-0005 section 5.5)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from aios.database.repositories import EventLogRepository
from aios.events.event import Event, EventPriority, EventStatus

pytestmark = pytest.mark.unit


class TestEventLogRepository:
    async def test_save_and_get(self, session_factory) -> None:
        repo = EventLogRepository(session_factory)
        event = Event(
            source="test-agent",
            event_type="DATA_UPDATED",
            payload={"symbol": "AAPL"},
            priority=EventPriority.HIGH,
        )
        await repo.save(event)
        restored = await repo.get(event.event_id)
        assert restored is not None
        assert restored.event_id == event.event_id
        assert restored.source == "test-agent"
        assert restored.event_type == "DATA_UPDATED"
        assert restored.payload == {"symbol": "AAPL"}
        assert restored.priority is EventPriority.HIGH

    async def test_get_missing_returns_none(self, session_factory) -> None:
        repo = EventLogRepository(session_factory)
        assert await repo.get(uuid4()) is None

    async def test_save_preserves_status(self, session_factory) -> None:
        repo = EventLogRepository(session_factory)
        event = Event(source="test", event_type="E1", status=EventStatus.DISPATCHED)
        await repo.save(event)
        restored = await repo.get(event.event_id)
        assert restored is not None
        assert restored.status is EventStatus.DISPATCHED

    async def test_multiple_events_distinct(self, session_factory) -> None:
        repo = EventLogRepository(session_factory)
        first = Event(source="a", event_type="E1")
        second = Event(source="b", event_type="E2")
        await repo.save(first)
        await repo.save(second)
        assert (await repo.get(first.event_id)).event_id == first.event_id
        assert (await repo.get(second.event_id)).event_id == second.event_id
