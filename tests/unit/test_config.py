"""Configuration module tests (ADR-0011 unit test category).

Verifies:
    - ``config/config.development.toml`` can be read and parsed.
    - ``AIOS_ENVIRONMENT`` is required and validated (ADR-0009 section 5.4).
    - Configuration files contain no secrets (ADR-0009 section 5.6).
"""

from __future__ import annotations

import pytest

from aios.config.errors import ConfigError
from aios.config.loader import TomlSettingsLoader, get_environment, load_settings
from aios.config.settings import Environment, LoggingDestination, LoggingFormat

pytestmark = pytest.mark.unit


class TestEnvironment:
    def test_missing_environment_variable_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AIOS_ENVIRONMENT", raising=False)
        with pytest.raises(ConfigError, match="AIOS_ENVIRONMENT"):
            get_environment()

    def test_unsupported_environment_value_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "staging")
        with pytest.raises(ConfigError, match="Unsupported"):
            get_environment()

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("development", Environment.DEVELOPMENT),
            ("testing", Environment.TESTING),
            ("paper", Environment.PAPER),
            ("production", Environment.PRODUCTION),
        ],
    )
    def test_supported_environment_values(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: Environment
    ) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", raw)
        assert get_environment() is expected


class TestTomlSettingsLoader:
    def test_development_config_loads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        settings = TomlSettingsLoader(Environment.DEVELOPMENT).load()
        assert settings["app"]["environment"] == "development"
        assert settings["app"]["name"] == "aios"

    def test_missing_config_file_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        loader = TomlSettingsLoader(Environment.DEVELOPMENT, config_dir=tmp_path)
        with pytest.raises(ConfigError, match="not found"):
            loader.load()


class TestLoggingConfiguration:
    def test_development_uses_human_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        settings = load_settings()
        assert settings.logging.level == "DEBUG"
        assert settings.logging.format is LoggingFormat.HUMAN
        assert settings.logging.destination is LoggingDestination.CONSOLE

    def test_paper_uses_json_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "paper")
        settings = load_settings()
        assert settings.logging.format is LoggingFormat.JSON
        assert settings.logging.destination is LoggingDestination.FILE
        assert settings.logging.file_path == "logs/aios.log"

    def test_production_uses_json_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "production")
        settings = load_settings()
        assert settings.logging.format is LoggingFormat.JSON
        assert settings.logging.destination is LoggingDestination.FILE
        assert settings.logging.file_backup_count == 5


class TestConfigPrecedence:
    """Proves ADR-0009 section 5.2: env vars > TOML files > defaults.

    These tests exercise ``load_settings`` so that the precedence is
    demonstrated end-to-end for both the database and logging sections.
    """

    # Environment variable wins over the same key present in TOML.

    def test_database_env_overrides_toml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
        monkeypatch.setenv("AIOS_DATABASE_HOST", "env-host")
        settings = load_settings()
        assert settings.database.host == "env-host"

    def test_logging_env_overrides_toml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.setenv("AIOS_LOGGING_LEVEL", "WARNING")
        settings = load_settings()
        assert settings.logging.level == "WARNING"

    def test_paper_logging_toml_overridden_by_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "paper")
        monkeypatch.setenv("AIOS_LOGGING_LEVEL", "DEBUG")
        settings = load_settings()
        assert settings.logging.level == "DEBUG"

    # TOML value wins over the model default when no env var is set.

    def test_database_toml_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.delenv("AIOS_DATABASE_NAME", raising=False)
        settings = load_settings()
        assert settings.database.name == "aios_development"

    def test_logging_toml_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.delenv("AIOS_LOGGING_LEVEL", raising=False)
        settings = load_settings()
        assert settings.logging.level == "DEBUG"

    # Model default applies when neither TOML nor env provides a value.

    def test_database_default_when_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.delenv("AIOS_DATABASE_DRIVER", raising=False)
        settings = load_settings()
        assert settings.database.driver == "postgresql+psycopg"

    def test_logging_default_when_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.delenv("AIOS_LOGGING_FILE_PATH", raising=False)
        settings = load_settings()
        assert settings.logging.file_path == "logs/aios.log"

    # Environment-only values still reach the models through load_settings.

    def test_database_url_env_applies_through_loader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
        settings = load_settings()
        assert settings.database.database_url == "postgresql+psycopg://u:p@db:5432/x"

    def test_database_password_env_applies_through_loader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
        monkeypatch.setenv("AIOS_DATABASE_PASSWORD", "s3cret")
        settings = load_settings()
        assert "s3cret" in settings.database.database_url


class TestSignalConfiguration:
    @pytest.mark.parametrize(
        "environment",
        [
            Environment.DEVELOPMENT,
            Environment.TESTING,
            Environment.PAPER,
            Environment.PRODUCTION,
        ],
    )
    def test_signal_section_loads_from_toml(self, monkeypatch, environment) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", environment.value)
        settings = load_settings()
        assert settings.signal.technical_weight == pytest.approx(0.70)
        assert settings.signal.news_weight == pytest.approx(0.30)
        assert settings.signal.buy_threshold == pytest.approx(0.65)
        assert settings.signal.sell_threshold == pytest.approx(0.35)
        assert settings.signal.min_confidence == pytest.approx(0.50)
        assert settings.signal.min_news_items == 1
        assert settings.signal.require_news is True

    def test_signal_env_overrides_toml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.setenv("AIOS_SIGNAL_BUY_THRESHOLD", "0.8")
        monkeypatch.setenv("AIOS_SIGNAL_REQUIRE_NEWS", "false")
        settings = load_settings()
        assert settings.signal.buy_threshold == pytest.approx(0.8)
        assert settings.signal.require_news is False

    def test_signal_toml_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        monkeypatch.delenv("AIOS_SIGNAL_TECHNICAL_WEIGHT", raising=False)
        settings = load_settings()
        assert settings.signal.technical_weight == pytest.approx(0.70)


class TestConfigFilesContainNoSecrets:
    @pytest.mark.parametrize(
        "environment",
        [
            Environment.DEVELOPMENT,
            Environment.TESTING,
            Environment.PAPER,
            Environment.PRODUCTION,
        ],
    )
    def test_loaded_config_has_no_secret_keys(self, environment: Environment) -> None:
        settings = TomlSettingsLoader(environment).load()
        lowered = {key.lower(): value for key, value in settings.items()}
        assert "password" not in lowered
        assert "secret" not in lowered
        assert "api_key" not in lowered
        assert "token" not in lowered
