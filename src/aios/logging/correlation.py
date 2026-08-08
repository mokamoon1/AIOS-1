"""Correlation identifiers for structured logging (ADR-0010 section 5.4).

Correlation identifiers — Request ID, Event ID, and Trace ID — propagate
across components through the Event Bus messages. Context variables carry
the active identifiers so that every log record emitted inside a correlation
scope is enriched with them.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass

_request_id: ContextVar[str | None] = ContextVar("aios_request_id", default=None)
_event_id: ContextVar[str | None] = ContextVar("aios_event_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("aios_trace_id", default=None)


@dataclass(frozen=True)
class Correlation:
    """Active correlation identifiers (ADR-0010 section 5.4)."""

    request_id: str | None = None
    event_id: str | None = None
    trace_id: str | None = None


def current_correlation() -> Correlation:
    """Return the currently active correlation identifiers."""
    return Correlation(
        request_id=_request_id.get(),
        event_id=_event_id.get(),
        trace_id=_trace_id.get(),
    )


@contextmanager
def correlation_scope(
    *,
    request_id: str | None = None,
    event_id: str | None = None,
    trace_id: str | None = None,
) -> Iterator[Correlation]:
    """Establish a correlation scope for the current async/sync context.

    Identifiers that are not provided keep their previously active values,
    so nested scopes compose correctly and may override only a subset. The
    identifiers are restored to their previous values when the scope exits.
    """
    current = current_correlation()
    effective = Correlation(
        request_id=request_id if request_id is not None else current.request_id,
        event_id=event_id if event_id is not None else current.event_id,
        trace_id=trace_id if trace_id is not None else current.trace_id,
    )
    tokens: list[Token[str | None]] = [
        _request_id.set(effective.request_id),
        _event_id.set(effective.event_id),
        _trace_id.set(effective.trace_id),
    ]
    try:
        yield effective
    finally:
        for token in reversed(tokens):
            token.var.reset(token)


class CorrelationFilter(logging.Filter):
    """Attach the active correlation identifiers to log records.

    The identifiers are injected as ``request_id``, ``event_id``, and
    ``trace_id`` attributes so that formatters may include them, and are
    available for correlation across components (ADR-0010 section 5.4).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        correlation = current_correlation()
        record.request_id = correlation.request_id  # type: ignore[attr-defined]
        record.event_id = correlation.event_id  # type: ignore[attr-defined]
        record.trace_id = correlation.trace_id  # type: ignore[attr-defined]
        return True
