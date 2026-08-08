"""Event bus exceptions (ADR-0005)."""

from __future__ import annotations

from aios.errors.exceptions import EventBusError


class EventValidationError(EventBusError):
    """Raised when an event fails validation before publication (ADR-0005)."""
