"""Database configuration tests (ADR-0001, ADR-0009).

Verifies that the database URL is read from configuration without any
credentials embedded in code or configuration files.
"""

from __future__ import annotations

import pytest

from aios.config import DatabaseSettings, load_settings

pytestmark = pytest.mark.unit


class TestDatabaseSettings:
    def test_default_database_url_is_postgres(self) -> None:
        settings = DatabaseSettings()
        assert settings.database_url.startswith("postgresql+psycopg://")

    def test_database_url_includes_password_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
        monkeypatch.setenv("AIOS_DATABASE_PASSWORD", "s3cret")
        settings = DatabaseSettings()
        assert settings.database_url == ("postgresql+psycopg://aios:s3cret@localhost:5432/aios")

    def test_database_url_without_password_omits_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
        monkeypatch.delenv("AIOS_DATABASE_PASSWORD", raising=False)
        settings = DatabaseSettings()
        assert settings.database_url == "postgresql+psycopg://aios@localhost:5432/aios"

    def test_database_url_override_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
        settings = DatabaseSettings()
        assert settings.database_url == "postgresql+psycopg://u:p@db:5432/x"


class TestDatabaseSettingsFromFiles:
    def test_development_config_loads_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_ENVIRONMENT", "development")
        settings = load_settings()
        assert settings.database.name == "aios_development"
        assert settings.database.database_url.startswith("postgresql+psycopg://")
