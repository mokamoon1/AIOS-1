"""Core Engine exceptions (AIOS-104).

These exceptions build on the unified :class:`AiosError` hierarchy so that
Core Engine failures — bootstrap, lifecycle, and state violations — are
handled uniformly across the platform (AIOS-104 section 7).
"""

from __future__ import annotations

from aios.errors import AiosError


class CoreError(AiosError):
    """Base class for Core Engine errors (AIOS-104 section 2)."""


class CoreStateError(CoreError):
    """Raised when the Core Engine lifecycle transition is invalid."""


class CoreBootstrapError(CoreError):
    """Raised when the Core Engine cannot complete startup (AIOS-104 section 4)."""
