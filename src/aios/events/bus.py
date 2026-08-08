"""Event Bus interface and in-process implementation (ADR-0005).

Phase 1 adopts an **In-Process Event Bus** behind a stable interface
(ADR-0005 section 5). The interface preserves the ability to replace the
implementation with an external broker without redesigning components
(ADR-0005 section 5.7).
"""

from __future__ import annotations

import logging
from typing import Protocol

from aios.events.event import Event
from aios.events.exceptions import EventValidationError
from aios.events.handlers import AsyncEventHandler
from aios.events.repository import EventRepository

logger = logging.getLogger(__name__)


class EventBus(Protocol):
    """Stable public interface of the AIOS Event Bus (ADR-0005 section 5).

    Publishing and delivery are asynchronous; publishers do not block on
    subscriber processing (ADR-0005 section 5.1).
    """

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its type."""
        ...

    def subscribe(self, event_type: str, handler: AsyncEventHandler) -> None:
        """Register a handler for a specific event type."""
        ...


class InMemoryEventBus:
    """Phase 1 in-process Event Bus (ADR-0005 section 5).

    Implements per-event-type subscriber dispatch. Every published event is
    persisted to the configured EventRepository *before* dispatch
    (save-before-publish, ADR-0005 section 5.5) when a repository is present.
    A failing subscriber must not crash the bus or block other subscribers
    (ADR-0005 section 5.6).
    """

    def __init__(self, repository: EventRepository | None = None) -> None:
        self._repository = repository
        self._subscribers: dict[str, list[AsyncEventHandler]] = {}

    def subscribe(self, event_type: str, handler: AsyncEventHandler) -> None:
        if not event_type.strip():
            raise EventValidationError("event_type must not be empty")
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Event) -> None:
        if self._repository is not None:
            await self._repository.save(event)

        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                if hasattr(handler, "handle"):
                    await handler.handle(event)  # type: ignore[union-attr]
                else:
                    await handler(event)  # type: ignore[operator]
            except Exception:
                logger.exception(
                    "Event handler failed for event_id=%s handler=%s",
                    event.event_id,
                    getattr(handler, "__qualname__", handler),
                )
