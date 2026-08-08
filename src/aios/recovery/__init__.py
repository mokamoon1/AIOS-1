"""Backup and recovery readiness package (AIOS-804, AIOS-107 section 9).

AIOS-804 defines the Backup and Recovery framework: the assets that must be
protected (section 3), a Backup Manager that coordinates operations (section
4), backup validation (section 7), and recovery procedures (section 8). The
approved documents specify these requirements without an implementation
contract (storage backend, schedule, or tooling), so this package provides
the documented integration point: the backup asset catalogue, the runtime
configuration, and the :class:`BackupManager` interface that concrete backup
implementations satisfy.
"""

from __future__ import annotations

from aios.recovery.interface import BackupError, BackupManager
from aios.recovery.models import BackupAsset, BackupSettings

__all__ = ["BackupAsset", "BackupError", "BackupManager", "BackupSettings"]
