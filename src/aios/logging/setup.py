"""Logging bootstrap and configuration (ADR-0010).

The Python standard logging framework is the official logging framework;
a thin helper configures consistent formatters and destinations based on the
environment configuration (ADR-0008 section 5.3, ADR-0010 section 5.1).
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from aios.config.settings import LoggingDestination, LoggingFormat, LoggingSettings
from aios.logging.correlation import CorrelationFilter
from aios.logging.formatters import HumanReadableFormatter, JsonFormatter
from aios.logging.masking import SensitiveDataFilter

_AUDIT_HANDLER_NAME = "aios.audit"


def _resolve_level(level: str) -> int:
    return getattr(logging, level)


def _build_formatter(settings: LoggingSettings) -> logging.Formatter:
    if settings.format is LoggingFormat.JSON:
        return JsonFormatter()
    return HumanReadableFormatter()


def _build_handler(settings: LoggingSettings) -> logging.Handler:
    formatter = _build_formatter(settings)
    if settings.destination is LoggingDestination.FILE:
        handler = _build_file_handler(settings)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())
    handler.addFilter(CorrelationFilter())
    return handler


def _build_file_handler(settings: LoggingSettings) -> logging.Handler:
    path = Path(settings.file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return logging.handlers.RotatingFileHandler(
        filename=str(path),
        maxBytes=settings.file_max_bytes,
        backupCount=settings.file_backup_count,
        encoding="utf-8",
    )


def setup_logging(settings: LoggingSettings) -> logging.Logger:
    """Configure the ``aios`` logger for the active environment.

    The formatter (human vs JSON) and destination (console vs rotating file)
    are selected from the environment configuration per ADR-0009 and
    ADR-0010. Returning the ``aios`` logger lets callers obtain a child
    logger via ``logger.getChild("events")`` while keeping a single source of
    truth for the root configuration.
    """
    root = logging.getLogger("aios")
    root.setLevel(_resolve_level(settings.level))
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.addHandler(_build_handler(settings))
    root.propagate = False
    return root


def setup_audit_handler(logger: logging.Logger) -> logging.Logger:
    """Attach the dedicated audit logger used to record governance events.

    Audit logging remains separate from normal application debugging logs
    (ADR-0008 section 5.5, ADR-0010 section 5.5). This returns the audit
    logger, which callers should emit to when recording decisions, security
    checks, permission violations, and risk events.
    """
    audit = logging.getLogger(_AUDIT_HANDLER_NAME)
    audit.propagate = False
    audit.setLevel(logging.INFO)
    return audit


def get_audit_logger() -> logging.Logger:
    """Return the dedicated audit logger (ADR-0010 section 5.5)."""
    return logging.getLogger(_AUDIT_HANDLER_NAME)
