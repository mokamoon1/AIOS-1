"""Event persistence interface (ADR-0005 section 5.5).

The in-process bus is not a durable queue: every published event shall be
persisted to the System Database Domain via an EventRepository *before*
dispatch (save-before-publish). This module declares only the interface;
the SQLAlchemy-backed implementation belongs to the database layer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aios.events.event import Event


@runtime_checkable
class EventRepository(Protocol):
    """Persistence interface for events (ADR-0005 section 5.5).

    Implementations must persist the full event structure defined in
    AIOS-103 (event_id, timestamp, source, event_type, payload, priority,
    status) using snake_case column names per AIOS-1103.
    """

    async def save(self, event: Event) -> None:
        """Persist an event to the event log before dispatch."""
        ...

    async def get(self, event_id: object) -> Event | None:
        """Retrieve a persisted event by its Event ID."""
        ...
