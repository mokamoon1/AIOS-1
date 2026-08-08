"""Generic repository base (AIOS-606, ADR-0001).

Implements the :class:`aios.database.repository.Repository` protocol against
a SQLAlchemy ORM model. Domain repositories extend this base and add
domain-specific read methods; they never contain business logic (AIOS-606
section 5).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aios.database.engine import session_scope

EntityT = TypeVar("EntityT")


class BaseRepository(Generic[EntityT]):
    """Repository over a single SQLAlchemy ORM model."""

    entity_type: type[EntityT]

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        if not self.entity_type:
            raise TypeError(f"{type(self).__name__} must define entity_type")
        self._session_factory = session_factory

    # -- Repository protocol (caller-provided session) --------------------

    def get(self, session: Session, entity_id: object) -> EntityT | None:
        return session.get(self.entity_type, entity_id)

    def list(self, session: Session) -> Sequence[EntityT]:
        return list(session.scalars(select(self.entity_type)).all())

    def add(self, session: Session, entity: EntityT) -> EntityT:
        session.add(entity)
        session.flush()
        return entity

    def update(self, session: Session, entity: EntityT) -> EntityT:
        session.add(entity)
        session.flush()
        return entity

    def delete(self, session: Session, entity_id: object) -> None:
        entity = self.get(session, entity_id)
        if entity is not None:
            session.delete(entity)
            session.flush()

    def iterator(self, session: Session) -> Iterator[EntityT]:
        yield from session.scalars(select(self.entity_type)).all()

    # -- managed-session helpers ------------------------------------------

    def _scalars(self, statement):
        with session_scope(self._session_factory) as session:
            return list(session.scalars(statement).all())

    def _first(self, statement):
        with session_scope(self._session_factory) as session:
            return session.scalars(statement).first()
