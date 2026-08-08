"""AIOS configuration management package (ADR-0008, ADR-0009)."""

from __future__ import annotations

from aios.config.errors import ConfigError
from aios.config.loader import (
    SettingsLoader,
    TomlSettingsLoader,
    get_environment,
    load_settings,
)
from aios.config.settings import AppSettings, DatabaseSettings, Environment

__all__ = [
    "AppSettings",
    "ConfigError",
    "DatabaseSettings",
    "Environment",
    "SettingsLoader",
    "TomlSettingsLoader",
    "get_environment",
    "load_settings",
]
