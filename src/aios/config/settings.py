"""Runtime settings model and environment enumeration.

Implements the application configuration foundation defined in ADR-0008 and
ADR-0009:
    - pydantic-settings as the configuration framework (ADR-0008 section 5.1).
    - Four operational environments (ADR-0009 section 5.8).
    - Environment variables override configuration files and default values
      (ADR-0009 section 5.2).
    - Secrets, including the database password, are provided exclusively
      through environment variables (ADR-0009 section 5.6).
    - Logging foundation per ADR-0010 (levels, formatter, destination).
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class Environment(str, Enum):
    """Supported operational environments (ADR-0009 section 5.8)."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PAPER = "paper"
    PRODUCTION = "production"


class LoggingFormat(str, Enum):
    """Structured logging output formats (ADR-0010 section 5.2).

    Production and Paper Trading use the machine-readable ``json`` format;
    Development and Testing use ``human`` for readability.
    """

    HUMAN = "human"
    JSON = "json"


class LoggingDestination(str, Enum):
    """Log output destination (ADR-0010 section 5.6).

    Development and Testing log to the console; Paper Trading and Production
    use rotating log files.
    """

    CONSOLE = "console"
    FILE = "file"


class LoggingSettings(BaseSettings):
    """Logging configuration per environment (ADR-0010).

    The formatter is selected through the environment configuration defined
    by ADR-0009. Environment variables with the ``AIOS_LOGGING_`` prefix
    override configuration file values (ADR-0009 section 5.2). No secrets
    may ever be written to logs (ADR-0010 section 5.7); the logging layer
    applies sensitive-data masking.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_LOGGING_", extra="ignore")

    level: str = "INFO"
    format: LoggingFormat = LoggingFormat.HUMAN
    destination: LoggingDestination = LoggingDestination.CONSOLE
    file_path: str = "logs/aios.log"
    file_max_bytes: int = 10_000_000
    file_backup_count: int = 5

    @field_validator("level")
    @classmethod
    def level_must_be_supported(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _LOG_LEVELS:
            raise ValueError(
                f"Unsupported logging level {value!r}. "
                f"Valid values: {', '.join(sorted(_LOG_LEVELS))}."
            )
        return normalized


class DatabaseSettings(BaseSettings):
    """Database connection settings (ADR-0001, ADR-0006).

    PostgreSQL is the primary database (ADR-0001). The connection URL is
    built from individual parts; the password is read only from the
    ``AIOS_DATABASE_PASSWORD`` environment variable and is never stored in
    configuration files or source code (ADR-0009 section 5.6).

    A complete connection string may override all parts through the
    ``AIOS_DATABASE_URL`` environment variable (highest priority).
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_DATABASE_", extra="ignore")

    driver: str = "postgresql+psycopg"
    host: str = "localhost"
    port: int = 5432
    name: str = "aios"
    user: str = "aios"
    password: str | None = None
    url: str | None = Field(default=None, validation_alias="AIOS_DATABASE_URL")

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy connection URL for this database.

        An explicit ``AIOS_DATABASE_URL`` overrides the parts-based URL.
        Otherwise the URL is built from the configured driver, user,
        password, host, port, and database name.
        """
        if self.url:
            return self.url
        credentials = f":{self.password}" if self.password else ""
        return f"{self.driver}://{self.user}{credentials}@{self.host}:{self.port}/{self.name}"


class AppSettings(BaseSettings):
    """Application settings resolved through pydantic-settings.

    Configuration source priority (ADR-0009 section 5.2):
        1. Environment variables (highest, prefix ``AIOS_``).
        2. Environment-specific configuration files.
        3. Default safe values (lowest).

    ``environment`` records the active runtime environment identified through
    the mandatory ``AIOS_ENVIRONMENT`` variable (ADR-0009 section 5.4) so
    configuration remains explicitly traceable to its environment.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_", extra="ignore")

    app_name: str = "aios"
    environment: Environment | None = None
    debug: bool = False
    database: DatabaseSettings = DatabaseSettings()
    logging: LoggingSettings = LoggingSettings()
