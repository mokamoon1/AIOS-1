"""Error event publisher tests (AIOS-104 section 7, AIOS-408 section 11)."""

from __future__ import annotations

import pytest

from aios.errors import ErrorEventPublisher
from aios.events import Event, EventPriority, InMemoryEventBus
from aios.events.handlers import EventHandler

pytestmark = pytest.mark.unit


class RecordingHandler(EventHandler):
    def __init__(self) -> None:
        self.received: list[Event] = []

    async def handle(self, event: Event) -> None:
        self.received.append(event)


class TestErrorEventPublisher:
    async def test_publishes_error_event(self) -> None:
        bus = InMemoryEventBus()
        handler = RecordingHandler()
        bus.subscribe("ERROR", handler)
        publisher = ErrorEventPublisher(bus)

        event = await publisher.publish(
            source="test-suite",
            component="market-engine",
            error_type="ProviderError",
            message="provider timeout",
            details={"attempt": 3},
        )

        assert event.event_type == "ERROR"
        payload = handler.received[0].payload
        assert payload["component"] == "market-engine"
        assert payload["error_type"] == "ProviderError"
        assert payload["message"] == "provider timeout"
        assert payload["details"] == {"attempt": 3}

    async def test_error_events_are_high_priority(self) -> None:
        bus = InMemoryEventBus()
        handler = RecordingHandler()
        bus.subscribe("ERROR", handler)
        publisher = ErrorEventPublisher(bus)

        await publisher.publish(
            source="test-suite",
            component="risk-engine",
            error_type="SecurityError",
            message="access denied",
        )

        assert handler.received[0].priority is EventPriority.HIGH

    async def test_sensitive_values_are_masked(self) -> None:
        bus = InMemoryEventBus()
        handler = RecordingHandler()
        bus.subscribe("ERROR", handler)
        publisher = ErrorEventPublisher(bus)

        await publisher.publish(
            source="test-suite",
            component="broker",
            error_type="ProviderError",
            message="authentication failed password=secret-key",
        )

        message = handler.received[0].payload["message"]
        assert "password=[REDACTED]" in message
        assert "secret-key" not in message
