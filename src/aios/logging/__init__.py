"""AIOS logging and observability package (ADR-0008, ADR-0010).

Provides a thin helper over the Python standard logging framework:
    - Structured formatters (human for Development/Testing, JSON for
      Paper/Production) per ADR-0010 section 5.2.
    - Correlation identifiers (Request ID, Event ID, Trace ID) per
      ADR-0010 section 5.4.
    - Sensitive-data masking per ADR-0010 section 5.7.
    - A dedicated audit logger separate from diagnostic logs per
      ADR-0010 section 5.5.
"""

from __future__ import annotations

from aios.logging.audit import AuditEventPublisher
from aios.logging.correlation import (
    Correlation,
    CorrelationFilter,
    correlation_scope,
    current_correlation,
)
from aios.logging.formatters import HumanReadableFormatter, JsonFormatter
from aios.logging.masking import SensitiveDataFilter, mask_sensitive
from aios.logging.setup import (
    get_audit_logger,
    setup_audit_handler,
    setup_logging,
)

__all__ = [
    "AuditEventPublisher",
    "Correlation",
    "CorrelationFilter",
    "HumanReadableFormatter",
    "JsonFormatter",
    "SensitiveDataFilter",
    "correlation_scope",
    "current_correlation",
    "get_audit_logger",
    "mask_sensitive",
    "setup_audit_handler",
    "setup_logging",
]
