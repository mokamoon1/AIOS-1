"""Backup Manager interface tests (AIOS-804 sections 4, 7, and 8).

The approved documents define a Backup Manager with coordinated backup,
verification, and recovery operations but no concrete storage contract, so
this package exposes the interface as the documented integration point. The
tests verify the interface contract is structurally satisfiable without
inventing a backup engine.
"""

from __future__ import annotations

import pytest

from aios.errors import AiosError
from aios.recovery.interface import BackupError, BackupManager
from aios.recovery.models import BackupAsset

pytestmark = pytest.mark.unit


class StubBackupManager:
    """Minimal structural implementation of :class:`BackupManager`."""

    def create_backup(self, assets: set[BackupAsset] | None = None) -> str:
        del assets
        return "backup-001"

    def verify_backup(self, backup_id: str) -> bool:
        del backup_id
        return True

    def restore(self, backup_id: str) -> None:
        del backup_id
        return None


def accepts_manager(manager: BackupManager) -> bool:
    """Type-checked contract: any concrete backup implementation must conform."""
    backup_id = manager.create_backup()
    assert manager.verify_backup(backup_id) is True
    manager.restore(backup_id)
    return True


class TestBackupManagerInterface:
    def test_structural_conformance(self) -> None:
        assert accepts_manager(StubBackupManager()) is True

    def test_interface_operations_cover_documented_flow(self) -> None:
        """AIOS-804 section 4 (create), section 7 (verify), section 8 (restore)."""
        methods = {name for name in dir(BackupManager) if not name.startswith("_")}
        assert {"create_backup", "verify_backup", "restore"} <= methods

    def test_create_backup_accepts_asset_subset(self) -> None:
        backup_id = StubBackupManager().create_backup(assets={BackupAsset.DATABASE})
        assert backup_id == "backup-001"


class TestBackupError:
    def test_is_aios_error(self) -> None:
        assert issubclass(BackupError, AiosError)
        with pytest.raises(AiosError):
            raise BackupError("backup failed")
