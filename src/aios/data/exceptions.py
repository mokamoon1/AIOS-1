"""Data Layer exceptions (AIOS-501, AIOS-505, AIOS-506)."""

from __future__ import annotations

from aios.errors import DataError


class DataValidationError(DataError):
    """Raised when a dataset fails validation (AIOS-506 section 6).

    Invalid datasets shall not continue through the pipeline (AIOS-505
    section 5); this error stops ingestion before storage.
    """


class DataPipelineError(DataError):
    """Raised when a Data Pipeline stage fails (AIOS-505 section 10).

    Pipeline failures shall record logs, retry when appropriate, notify
    monitoring, and prevent invalid data from reaching analysis engines.
    """


class DataNotFoundError(DataError):
    """Raised when requested data does not exist in storage."""
