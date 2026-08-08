"""Configuration error types."""

from __future__ import annotations

from aios.errors.exceptions import ConfigurationError


class ConfigError(ConfigurationError):
    """Raised when runtime configuration cannot be resolved.

    Used for missing or invalid environment identification and missing or
    invalid configuration files (ADR-0009 sections 5.4 and 5.5).
    """
