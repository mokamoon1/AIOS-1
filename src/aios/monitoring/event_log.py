"""In-process operational event log feeding the alerting system (Phase 9.6).

The alert conditions must be driven by real, recorded system events rather
than hard-coded ``False`` returns. This module provides a small, thread-safe,
in-process event log that components record into synchronously (the broker
service is synchronous) and the :class:`AlertManager` reads from to evaluate
its rules (error rate, broker disconnect, Shariah violations, gate failures,
market-closed blocks).

The log is deliberately transport-free: it is the durable in-memory fact
source for the current process. Publishing the same facts onto the Event Bus
remains the responsibility of the components that record them.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("aios.monitoring.event_log")


def _aware(value: datetime) -> datetime:
    """Return ``value`` normalized to a UTC-aware datetime.

    Naive timestamps (e.g. ``datetime.utcnow()``) are interpreted as UTC so
    window queries compare consistently regardless of the recording source.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

# Well-known event types recorded into the log.
EVENT_ERROR = "ERROR"
EVENT_OPERATION = "OPERATION"
EVENT_BROKER_CONNECTED = "BROKER_CONNECTED"
EVENT_BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
EVENT_SHARIAH_VIOLATION = "SHARIAH_VIOLATION"
EVENT_GATE_FAILURE = "GATE_FAILURE"
EVENT_EMERGENCY_STOP = "EMERGENCY_STOP"
EVENT_EMERGENCY_CLEAR = "EMERGENCY_CLEAR"
EVENT_MARKET_CLOSED = "MARKET_CLOSED"
EVENT_ORDER_TIMEOUT = "ORDER_TIMEOUT"
EVENT_LATENCY_SAMPLE = "LATENCY_SAMPLE"


@dataclass(frozen=True)
class EventEntry:
    """A single recorded operational event."""

    event_type: str
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)


class EventLog:
    """Bounded, thread-safe log of operational events.

    Events are appended in insertion order and retained up to ``maxlen``
    entries. Windowed queries (``count_in_window``, ``has_recent``) let alert
    rules measure recent activity without retaining unbounded history.
    """

    def __init__(self, *, maxlen: int = 5000, logger: logging.Logger | None = None) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._maxlen = maxlen
        self._entries: deque[EventEntry] = deque()
        self._lock = threading.Lock()
        self._logger = logger or logging.getLogger("aios.monitoring.event_log")

    @property
    def maxlen(self) -> int:
        """Maximum number of retained entries."""
        return self._maxlen

    def record(
        self,
        event_type: str,
        source: str,
        *,
        payload: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> EventEntry:
        """Record an event and return it."""
        entry = EventEntry(
            event_type=event_type,
            source=source,
            timestamp=_aware(at or datetime.now(timezone.utc)),
            payload=payload or {},
        )
        with self._lock:
            self._entries.append(entry)
            while len(self._entries) > self._maxlen:
                self._entries.popleft()
        return entry

    def entries(self, event_type: str | None = None) -> list[EventEntry]:
        """Return recorded entries, newest last, optionally filtered by type."""
        with self._lock:
            entries = list(self._entries)
        if event_type is None:
            return entries
        return [entry for entry in entries if entry.event_type == event_type]

    def count_since(self, event_type: str, *, since: datetime) -> int:
        """Count entries of ``event_type`` recorded at or after ``since``."""
        cutoff = _aware(since)
        with self._lock:
            return sum(
                1
                for entry in self._entries
                if entry.event_type == event_type and entry.timestamp >= cutoff
            )

    def count_in_window(
        self, event_type: str, window_seconds: int, *, now: datetime | None = None
    ) -> int:
        """Count entries of ``event_type`` within the trailing time window."""
        reference = now or datetime.now(timezone.utc)
        since = reference - timedelta(seconds=window_seconds)
        return self.count_since(event_type, since=since)

    def has_recent(
        self, event_type: str, window_seconds: int, *, now: datetime | None = None
    ) -> bool:
        """Return whether ``event_type`` was recorded within the window."""
        return self.count_in_window(event_type, window_seconds, now=now) > 0

    def latest(self, event_type: str) -> EventEntry | None:
        """Return the most recent entry of ``event_type``, if any."""
        with self._lock:
            for entry in reversed(self._entries):
                if entry.event_type == event_type:
                    return entry
        return None

    def total(self) -> int:
        """Return the total number of retained entries."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Clear all retained entries."""
        with self._lock:
            self._entries.clear()
