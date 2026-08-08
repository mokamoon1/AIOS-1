"""Backup asset catalogue and runtime configuration (AIOS-804).

AIOS-804 section 3 defines the assets that must be included in backups;
section 6 documents a recommended schedule but no numeric retention contract,
so no retention values are introduced here (AIOS-804 section 11). Secrets are
never part of backup configuration: sensitive values remain exclusive to
environment variables (ADR-0009 section 5.6).
"""

from __future__ import annotations

from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackupAsset(str, Enum):
    """Assets that must be included in backups (AIOS-804 section 3)."""

    DATABASE = "database"
    CONFIGURATION = "configuration"
    ENVIRONMENT_TEMPLATES = "environment_templates"
    DOCUMENTATION = "documentation"
    STRATEGY_DEFINITIONS = "strategy_definitions"
    HISTORICAL_DATASETS = "historical_datasets"
    LOGS = "logs"
    RELEASE_ARTIFACTS = "release_artifacts"


class BackupSettings(BaseSettings):
    """Backup configuration for the active environment (AIOS-804).

    Structural settings only: whether backup procedures are enabled and where
    backups are stored. No schedule, retention period, or storage backend is
    configured here because the approved documents leave those operational
    details open (AIOS-804 sections 6 and 11).
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_BACKUP_", extra="ignore")

    enabled: bool = False
    directory: str = "backups"
