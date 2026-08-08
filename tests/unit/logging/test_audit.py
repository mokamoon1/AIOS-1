"""Audit event publisher tests (ADR-0010 section 5.5).

Verifies that governance events are emitted through the Event Bus as
audit records with a unique Event ID, separate from diagnostic logs.
"""

from __future__ import annotations

import pytest

from aios.events import Event, EventPriority, InMemoryEventBus
from aios.events.handlers import EventHandler
from aios.logging import AuditEventPublisher, correlation_scope

pytestmark = pytest.mark.unit


class RecordingHandler(EventHandler):
    def __init__(self) -> None:
        self.received: list[Event] = []

    async def handle(self, event: Event) -> None:
        self.received.append(event)


class TestAuditEventPublisher:
    async def test_publishes_audit_event(self) -> None:
        bus = InMemoryEventBus()
        handler = RecordingHandler()
        bus.subscribe("AUDIT", handler)
        publisher = AuditEventPublisher(bus)

        event = await publisher.publish(
            action="decision.created",
            subject="risk-manager",
            outcome="approved",
            source="test-suite",
            details={"limit": "reassigned"},
        )

        assert event is not None
        assert len(handler.received) == 1
        audit = handler.received[0]
        assert audit.event_type == "AUDIT"
        assert audit.source == "test-suite"
        assert audit.payload["action"] == "decision.created"
        assert audit.payload["subject"] == "risk-manager"
        assert audit.payload["outcome"] == "approved"
        assert audit.payload["details"] == {"limit": "reassigned"}

    async def test_audit_events_are_high_priority(self) -> None:
        bus = InMemoryEventBus()
        handler = RecordingHandler()
        bus.subscribe("AUDIT", handler)
        publisher = AuditEventPublisher(bus)

        await publisher.publish(
            action="permission.denied",
            subject="orders",
            outcome="denied",
            source="test-suite",
        )

        assert handler.received[0].priority is EventPriority.HIGH

    async def test_event_has_unique_id(self) -> None:
        bus = InMemoryEventBus()
        handler = RecordingHandler()
        bus.subscribe("AUDIT", handler)
        publisher = AuditEventPublisher(bus)

        await publisher.publish(action="a", subject="s", outcome="ok", source="test-suite")
        await publisher.publish(action="b", subject="s", outcome="ok", source="test-suite")

        first, second = handler.received
        assert first.event_id != second.event_id

    async def test_correlation_identifiers_in_payload(self) -> None:
        bus = InMemoryEventBus()
        handler = RecordingHandler()
        bus.subscribe("AUDIT", handler)
        publisher = AuditEventPublisher(bus)

        with correlation_scope(request_id="req-9", trace_id="trace-9"):
            await publisher.publish(
                action="risk.review", subject="portfolio", outcome="ok", source="test-suite"
            )

        payload = handler.received[0].payload
        assert payload["request_id"] == "req-9"
        assert payload["trace_id"] == "trace-9"
