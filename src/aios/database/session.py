"""Session management interface (ADR-0001, ADR-0006, AIOS-606).

Session lifecycle and transaction handling are managed here so that no
module outside the Database Layer communicates directly with the database
(AIOS-606 section 1).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker


class SessionManager(Protocol):
    """Interface for session lifecycle management."""

    def session_factory(self) -> sessionmaker[Session]:
        """Return the configured session factory."""
        ...

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a session with managed lifecycle."""
        ...
