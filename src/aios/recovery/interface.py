"""Backup Manager interface (AIOS-804).

AIOS-804 defines a Backup Manager that coordinates all backup operations
(section 4), requires every backup to be verified (section 7), and requires
recovery procedures to be documented and repeatable (section 8). The approved
documents leave the storage backend and scheduling open, so this module
defines the documented integration point: a :class:`BackupManager` protocol
that concrete backup implementations must satisfy. No backup engine is
invented here.
"""

from __future__ import annotations

from typing import Protocol

from aios.errors import AiosError
from aios.recovery.models import BackupAsset


class BackupError(AiosError):
    """Raised when a backup or recovery operation cannot complete safely."""


class BackupManager(Protocol):
    """Coordinates backup and recovery operations (AIOS-804 section 4).

    Implementations must:
    - ``create_backup`` capture the requested assets (section 4).
    - ``verify_backup`` validate file integrity, completeness, and recovery
      readiness (section 7); unverified backups are not considered valid.
    - ``restore`` perform a documented, repeatable recovery (section 8).
    """

    def create_backup(self, assets: set[BackupAsset] | None = None) -> str:
        """Create a backup of the requested assets and return its identifier.

        ``assets`` defaults to the full documented catalogue (AIOS-804
        section 3).
        """
        ...

    def verify_backup(self, backup_id: str) -> bool:
        """Return whether ``backup_id`` passed integrity validation (AIOS-804 section 7)."""
        ...

    def restore(self, backup_id: str) -> None:
        """Restore the system from ``backup_id`` (AIOS-804 section 8)."""
        ...
