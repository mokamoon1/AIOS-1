"""Event log repository (ADR-0005 section 5.5, ADR-0006 section 5.6).

SQLAlchemy-backed implementation of :class:`aios.events.repository.EventRepository`
for the System Database Domain. The Event Bus persists every event here
*before* dispatch (save-before-publish). Events are never deleted.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select

from aios.database.engine import session_scope
from aios.database.models import EventLogModel
from aios.database.repositories.base import BaseRepository
from aios.events.event import Event


class EventLogRepository(BaseRepository[EventLogModel]):
    """Persistent event log for the Event Bus."""

    entity_type = EventLogModel

    async def save(self, event: Event) -> None:
        """Persist ``event`` to the event log (ADR-0005 section 5.5)."""
        with session_scope(self._session_factory) as session:
            session.add(EventLogModel.from_event(event))

    async def get(self, event_id: object) -> Event | None:
        """Return the persisted event with ``event_id`` or ``None``."""
        with session_scope(self._session_factory) as session:
            row = session.execute(
                select(EventLogModel).where(EventLogModel.event_id == cast(UUID, event_id))
            ).scalar_one_or_none()
            return row.to_domain() if row is not None else None
