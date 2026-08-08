"""Settings loader interface and TOML configuration loading.

Implements the configuration file handling defined in ADR-0009:
    - Environment identification through the mandatory ``AIOS_ENVIRONMENT``
      environment variable (section 5.4).
    - Environment-specific TOML configuration files in ``config/`` named
      ``config.<environment>.toml`` (section 5.5).
    - Secrets are never stored in configuration files (section 5.6).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from aios.config.errors import ConfigError
from aios.config.settings import (
    AppSettings,
    DatabaseSettings,
    Environment,
    LoggingSettings,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

_CONFIG_DIR_NAME = "config"
_ENV_VAR_NAME = "AIOS_ENVIRONMENT"
_SUPPORTED_ENVIRONMENTS = frozenset(env.value for env in Environment)

_SECRET_KEYS = frozenset({"password", "secret", "api_key", "token"})


@runtime_checkable
class SettingsLoader(Protocol):
    """Interface for loading runtime settings (ADR-0009 section 5.1)."""

    def load(self) -> Mapping[str, Any]:
        """Return the resolved configuration mapping for the active environment."""
        ...


def get_environment() -> Environment:
    """Resolve the active environment from ``AIOS_ENVIRONMENT``.

    Raises:
        ConfigError: if the variable is missing or contains an unsupported value.
    """
    raw = os.environ.get(_ENV_VAR_NAME)
    if raw is None:
        raise ConfigError(
            f"Environment variable {_ENV_VAR_NAME!r} is not set. "
            f"Valid values: {', '.join(sorted(_SUPPORTED_ENVIRONMENTS))}."
        )
    value = raw.strip().lower()
    if value not in _SUPPORTED_ENVIRONMENTS:
        raise ConfigError(
            f"Unsupported {_ENV_VAR_NAME}={raw!r}. "
            f"Valid values: {', '.join(sorted(_SUPPORTED_ENVIRONMENTS))}."
        )
    return Environment(value)


def config_file_for(environment: Environment, config_dir: Path | None = None) -> Path:
    """Return the TOML configuration file path for the given environment."""
    directory = config_dir or _default_config_dir()
    return directory / f"config.{environment.value}.toml"


def _default_config_dir() -> Path:
    """Return the project-level ``config/`` directory.

    ``src/aios/config/loader.py`` is three levels below the project root, so
    the project root is reached by walking three parents from this module.
    """
    return Path(__file__).resolve().parents[3] / _CONFIG_DIR_NAME


class TomlSettingsLoader:
    """Loads runtime settings from an environment-specific TOML file.

    Implements the :class:`SettingsLoader` interface for TOML files
    (ADR-0009 sections 5.3 and 5.5). Only non-secret keys are returned;
    secrets are supplied exclusively through environment variables.
    """

    def __init__(self, environment: Environment, config_dir: Path | None = None) -> None:
        self._path = config_file_for(environment, config_dir)

    def load(self) -> Mapping[str, Any]:
        if not self._path.is_file():
            raise ConfigError(f"Configuration file not found: {self._path}")
        with self._path.open("rb") as handle:
            try:
                data = tomllib.load(handle)
            except tomllib.TOMLDecodeError as exc:
                raise ConfigError(f"Invalid TOML in {self._path}: {exc}") from exc
        return _without_secrets(data)


def load_settings(
    environment: Environment | None = None, config_dir: Path | None = None
) -> AppSettings:
    """Load full application settings for the active environment.

    Combines the three configuration sources with the precedence mandated by
    ADR-0009 section 5.2 (highest first): environment variables, then
    environment-specific TOML files, then default values.

    TOML values are merged with environment-variable overrides *before*
    models are constructed so that an environment variable always wins over
    the corresponding TOML value, even when both define the same key.
    """
    active = environment or get_environment()
    raw = TomlSettingsLoader(active, config_dir).load()

    app_section = dict(raw.get("app", {}))
    database_values = dict(raw.get("database", {}))
    logging_values = dict(raw.get("logging", {}))

    database_values.update(_env_overrides("AIOS_DATABASE_", exclude={"url"}))
    logging_values.update(_env_overrides("AIOS_LOGGING_"))

    return AppSettings(
        app_name=os.environ.get("AIOS_APP_NAME") or str(app_section.get("name", "aios")),
        environment=active,
        debug=_env_bool("AIOS_DEBUG", bool(app_section.get("debug", False))),
        database=DatabaseSettings(**database_values),
        logging=LoggingSettings(**logging_values),
    )


def _env_bool(key: str, default: bool) -> bool:
    """Return the environment variable ``key`` parsed as a boolean.

    ``AIOS_DEBUG`` wins over the TOML value (ADR-0009 section 5.2); absent
    or empty values fall back to ``default``.
    """
    value = os.environ.get(key)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_overrides(prefix: str, exclude: set[str] | None = None) -> dict[str, str]:
    """Return environment variables for ``prefix`` keyed by field name.

    Environment variables override TOML configuration (ADR-0009 section
    5.2), so the loader applies them on top of the TOML values. Fields in
    ``exclude`` are left to the model to resolve from its own environment
    source (e.g. ``AIOS_DATABASE_URL`` via its validation alias).
    """
    excluded = exclude or set()
    overrides: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.upper().startswith(prefix):
            field_name = key[len(prefix) :].lower()
            if field_name and field_name not in excluded:
                overrides[field_name] = value
    return overrides


def _without_secrets(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the configuration without any secret values.

    Secret keys, defined in ADR-0009 section 5.6, are never expected inside
    configuration files; this guard keeps them out of the loaded settings.
    Nested sections are checked recursively so secrets cannot hide under
    any configuration table.
    """
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _SECRET_KEYS:
            continue
        if isinstance(value, Mapping):
            cleaned[key] = _without_secrets(value)
        else:
            cleaned[key] = value
    return cleaned
