"""Database layer exceptions (ADR-0001, ADR-0006, AIOS-606)."""

from __future__ import annotations

from aios.errors.exceptions import DatabaseError


class DatabaseConnectionError(DatabaseError):
    """Raised when a database connection cannot be established."""


class DatabaseOperationalError(DatabaseError):
    """Raised when a database operation fails."""


class DatabaseIntegrityError(DatabaseError):
    """Raised when a database integrity constraint is violated."""


class RecordNotFoundError(DatabaseError):
    """Raised when a requested record does not exist."""
