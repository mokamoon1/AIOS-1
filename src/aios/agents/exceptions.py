"""Agent-specific exceptions (AIOS-604).

These exceptions build on the unified :class:`AgentError` so agent failures
remain part of the AIOS error hierarchy (AIOS-104 section 7) while giving
the framework precise failure categories for lifecycle, registration, and
lookup errors.
"""

from __future__ import annotations

from aios.errors import AgentError


class AgentStateError(AgentError):
    """Raised when an agent lifecycle transition is invalid (AIOS-604 section 6)."""


class AgentRegistrationError(AgentError):
    """Raised when an agent cannot be registered with the Agent Manager."""


class AgentNotFoundError(AgentError):
    """Raised when an agent lookup fails (AIOS-604 section 5)."""
