"""Structured log formatters (ADR-0010 section 5.2).

Development and Testing use the human-readable formatter; Paper Trading and
Production use the machine-readable JSON formatter so that logs can be
consumed by monitoring and audit tooling.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from aios.logging.correlation import Correlation, current_correlation


def _correlation_fields(correlation: Correlation) -> dict[str, str]:
    fields: dict[str, str] = {}
    if correlation.request_id:
        fields["request_id"] = correlation.request_id
    if correlation.event_id:
        fields["event_id"] = correlation.event_id
    if correlation.trace_id:
        fields["trace_id"] = correlation.trace_id
    return fields


class JsonFormatter(logging.Formatter):
    """Emit a single JSON object per record (ADR-0010 sections 5.2 and 5.3).

    Fields: timestamp, level, component, message, and any active correlation
    identifiers. Exception details are included as a string when present.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        payload.update(_correlation_fields(current_correlation()))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable console formatter (ADR-0010 section 5.2).

    Includes active correlation identifiers as a suffix so context remains
    visible in Development and Testing.
    """

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        correlation = _correlation_fields(current_correlation())
        if correlation:
            suffix = " ".join(f"{key}={value}" for key, value in correlation.items())
            return f"{base} [{suffix}]"
        return base
