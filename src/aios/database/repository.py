"""Repository Pattern interface (ADR-0001, ADR-0006, AIOS-606).

Every domain exposes its own repository. Repositories provide a stable
interface independent of the underlying database (AIOS-606 section 5).
Domain repositories are concrete implementations of :class:`Repository`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Generic, Protocol, TypeVar, runtime_checkable

from sqlalchemy.orm import Session

EntityT = TypeVar("EntityT")
IdT = TypeVar("IdT", contravariant=True)


@runtime_checkable
class Repository(Protocol, Generic[EntityT, IdT]):
    """Repository interface skeleton for AIOS domain repositories.

    Concrete repositories implement these operations using SQLAlchemy
    sessions. No module outside the Database Layer communicates directly
    with the database (ADR-0001, AIOS-606).
    """

    def get(self, session: Session, entity_id: IdT) -> EntityT | None:
        """Return the entity with ``entity_id`` or ``None`` if absent."""
        ...

    def list(self, session: Session) -> Sequence[EntityT]:
        """Return all entities."""
        ...

    def add(self, session: Session, entity: EntityT) -> EntityT:
        """Persist a new entity and return it."""
        ...

    def update(self, session: Session, entity: EntityT) -> EntityT:
        """Persist changes to an existing entity and return it."""
        ...

    def delete(self, session: Session, entity_id: IdT) -> None:
        """Delete the entity with ``entity_id``."""
        ...

    def iterator(self, session: Session) -> Iterator[EntityT]:
        """Return an iterator over all entities."""
        ...
