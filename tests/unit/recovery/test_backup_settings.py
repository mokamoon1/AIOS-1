"""Backup settings and asset catalogue tests (AIOS-804 sections 3 and 6).

Verifies the documented backup asset list, the structural runtime
configuration, and that backup configuration carries no secret fields
(ADR-0009 section 5.6).
"""

from __future__ import annotations

import pytest

from aios.recovery.models import BackupAsset, BackupSettings

pytestmark = pytest.mark.unit


class TestBackupAssetCatalogue:
    def test_assets_match_documented_scope(self) -> None:
        """AIOS-804 section 3 lists eight assets that backups must cover."""
        documented = {
            "database",
            "configuration",
            "environment_templates",
            "documentation",
            "strategy_definitions",
            "historical_datasets",
            "logs",
            "release_artifacts",
        }
        assert {asset.value for asset in BackupAsset} == documented


class TestBackupSettings:
    def test_defaults(self) -> None:
        settings = BackupSettings()
        assert settings.enabled is False
        assert settings.directory == "backups"

    def test_environment_variable_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_BACKUP_ENABLED", "true")
        monkeypatch.setenv("AIOS_BACKUP_DIRECTORY", "backups/production")
        settings = BackupSettings()
        assert settings.enabled is True
        assert settings.directory == "backups/production"

    def test_no_secret_fields(self) -> None:
        """Backup configuration must never hold credentials (ADR-0009 section 5.6)."""
        fields = BackupSettings.model_fields
        assert "password" not in fields
        assert "api_key" not in fields
        assert "token" not in fields
        assert "secret" not in fields
