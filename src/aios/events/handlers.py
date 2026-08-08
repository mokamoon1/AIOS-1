"""Event handler protocol (ADR-0005).

A handler processes a single event on behalf of a subscriber. Handlers must
be idempotent by Event ID to tolerate redelivery (ADR-0005 section 5.3).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol, runtime_checkable

from aios.events.event import Event


@runtime_checkable
class EventHandler(Protocol):
    """Protocol for event handler callables.

    Subscribers may register any object implementing ``async handle(event)``.
    A failing handler must not crash the bus or block other subscribers
    (ADR-0005 section 5.6).
    """

    async def handle(self, event: Event) -> None: ...


@runtime_checkable
class EventHandlerCallable(Protocol):
    """Protocol for bare async callables usable as handlers."""

    async def __call__(self, event: Event) -> None: ...


AsyncEventHandler = EventHandler | EventHandlerCallable | Awaitable[None]
