"""Safe error handling tests (AIOS-104 section 7, AIOS-604 section 15)."""

from __future__ import annotations

import logging

import pytest

from aios.errors import (
    ErrorEventPublisher,
    ProviderError,
    capture_error,
    safe_call,
    safe_call_async,
)
from aios.events import Event, InMemoryEventBus
from aios.events.handlers import EventHandler

pytestmark = pytest.mark.unit

logger = logging.getLogger("aios.errors.test")


class RecordingHandler(EventHandler):
    def __init__(self) -> None:
        self.received: list[Event] = []

    async def handle(self, event: Event) -> None:
        self.received.append(event)


def _publisher() -> tuple[InMemoryEventBus, RecordingHandler, ErrorEventPublisher]:
    bus = InMemoryEventBus()
    handler = RecordingHandler()
    bus.subscribe("ERROR", handler)
    return bus, handler, ErrorEventPublisher(bus)


class TestCaptureError:
    async def test_logs_and_reraises(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.ERROR), pytest.raises(ProviderError, match="boom"):
            async with capture_error(logger=logger, component="market-engine"):
                raise ProviderError("boom")
        assert "market-engine" in caplog.text
        assert "boom" in caplog.text

    async def test_notifies_event_bus(self) -> None:
        _, handler, publisher = _publisher()
        with pytest.raises(ProviderError):
            async with capture_error(
                logger=logger,
                component="market-engine",
                publisher=publisher,
            ):
                raise ProviderError("boom")
        assert len(handler.received) == 1
        payload = handler.received[0].payload
        assert payload["component"] == "market-engine"
        assert payload["error_type"] == "ProviderError"

    async def test_re_raise_false_swallows(self) -> None:
        result = "unreachable"
        async with capture_error(
            logger=logger,
            component="market-engine",
            re_raise=False,
        ):
            raise ProviderError("boom")
        assert result == "unreachable"


class TestSafeCallAsync:
    async def test_returns_result_on_success(self) -> None:
        async def work() -> str:
            return "ok"

        result = await safe_call_async(
            work, logger=logger, component="analysis-engine", default="fallback"
        )
        assert result == "ok"

    async def test_returns_default_on_failure(self) -> None:
        async def work() -> str:
            raise ProviderError("boom")

        result = await safe_call_async(
            work, logger=logger, component="analysis-engine", default="fallback"
        )
        assert result == "fallback"

    async def test_notifies_on_failure(self) -> None:
        _, handler, publisher = _publisher()

        async def work() -> str:
            raise ProviderError("boom")

        await safe_call_async(
            work,
            logger=logger,
            component="analysis-engine",
            publisher=publisher,
            default="fallback",
        )
        assert len(handler.received) == 1
        assert handler.received[0].payload["component"] == "analysis-engine"


class TestSafeCall:
    def test_returns_result_on_success(self) -> None:
        assert safe_call(lambda: "ok", logger=logger, component="x", default="d") == "ok"

    def test_returns_default_on_failure(self) -> None:
        def work() -> str:
            raise ProviderError("boom")

        assert safe_call(work, logger=logger, component="x", default="d") == "d"
