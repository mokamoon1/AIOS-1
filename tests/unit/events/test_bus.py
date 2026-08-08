"""Tests for the Event Bus publish/subscribe behavior (ADR-0005)."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from aios.events import Event, EventBus, InMemoryEventBus
from aios.events.exceptions import EventValidationError


class _RecordingHandler:
    def __init__(self) -> None:
        self.received: list[Event] = []

    async def handle(self, event: Event) -> None:
        self.received.append(event)


async def test_publish_dispatches_to_matching_subscriber() -> None:
    bus = InMemoryEventBus()
    handler = _RecordingHandler()
    bus.subscribe("MARKET_DATA_UPDATED", handler)
    event = Event(source="market", event_type="MARKET_DATA_UPDATED")

    await bus.publish(event)

    assert handler.received == [event]


async def test_subscriber_not_called_for_other_event_type() -> None:
    bus = InMemoryEventBus()
    handler = _RecordingHandler()
    bus.subscribe("PRICE_CHANGED", handler)
    event = Event(source="market", event_type="MARKET_DATA_UPDATED")

    await bus.publish(event)

    assert handler.received == []


async def test_publish_notifies_all_subscribers_of_same_type() -> None:
    bus = InMemoryEventBus()
    first = _RecordingHandler()
    second = _RecordingHandler()
    bus.subscribe("MARKET_DATA_UPDATED", first)
    bus.subscribe("MARKET_DATA_UPDATED", second)
    event = Event(source="market", event_type="MARKET_DATA_UPDATED")

    await bus.publish(event)

    assert first.received == [event]
    assert second.received == [event]


async def test_failing_handler_does_not_block_other_subscribers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = InMemoryEventBus()

    async def broken_handler(event: Event) -> None:
        raise RuntimeError("boom")

    healthy = _RecordingHandler()
    bus.subscribe("MARKET_DATA_UPDATED", broken_handler)
    bus.subscribe("MARKET_DATA_UPDATED", healthy)
    event = Event(source="market", event_type="MARKET_DATA_UPDATED")

    with caplog.at_level(logging.ERROR):
        await bus.publish(event)

    assert healthy.received == [event]
    assert "Event handler failed" in caplog.text


async def test_publish_persists_before_dispatch() -> None:
    repository = AsyncMock()
    bus = InMemoryEventBus(repository=repository)
    handler = _RecordingHandler()
    bus.subscribe("MARKET_DATA_UPDATED", handler)
    event = Event(source="market", event_type="MARKET_DATA_UPDATED")

    await bus.publish(event)

    repository.save.assert_awaited_once_with(event)
    assert handler.received == [event]


async def test_subscribe_with_empty_event_type_raises() -> None:
    bus = InMemoryEventBus()

    with pytest.raises(EventValidationError):
        bus.subscribe("  ", lambda event: None)  # type: ignore[arg-type]


async def test_event_bus_is_protocol_compatible() -> None:
    def check(interface: type[EventBus]) -> None:
        assert hasattr(interface, "publish")
        assert hasattr(interface, "subscribe")

    check(EventBus)
    check(InMemoryEventBus)


async def test_bare_callable_handler() -> None:
    bus = InMemoryEventBus()
    received: list[Event] = []

    async def on_event(event: Event) -> None:
        received.append(event)

    bus.subscribe("MARKET_DATA_UPDATED", on_event)
    event = Event(source="market", event_type="MARKET_DATA_UPDATED")

    await bus.publish(event)

    assert received == [event]
