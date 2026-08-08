"""Engine-specific exceptions (AIOS-605).

These exceptions build on the unified :class:`EngineError` so engine
failures remain part of the AIOS error hierarchy (AIOS-104 section 7) while
giving the framework precise failure categories for lifecycle, registration,
validation, and lookup errors.
"""

from __future__ import annotations

from aios.errors import EngineError


class EngineStateError(EngineError):
    """Raised when an engine lifecycle transition is invalid (AIOS-605 section 4)."""


class EngineRegistrationError(EngineError):
    """Raised when an engine cannot be registered with the Engine Manager."""


class EngineNotFoundError(EngineError):
    """Raised when an engine lookup fails (AIOS-605 section 3)."""


class EngineValidationError(EngineError):
    """Raised when engine input or output fails validation (AIOS-605 section 15)."""


class EngineDependencyError(EngineError):
    """Raised when engine execution-order resolution detects a cycle (AIOS-605 section 3)."""
