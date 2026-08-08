"""Provider-specific exceptions (AIOS-603 section 6).

These exceptions build on the unified :class:`ProviderError` so provider
failures remain part of the AIOS error hierarchy (AIOS-104 section 7).
"""

from __future__ import annotations

from aios.errors import ProviderError


class ProviderRegistrationError(ProviderError):
    """Raised when a provider cannot be registered with the Provider Manager."""


class ProviderNotFoundError(ProviderError):
    """Raised when a provider lookup fails (AIOS-104 section 5.2)."""
