"""EventLog tests (Phase 9.6, P0-1 foundation)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.monitoring.event_log import (
    EVENT_ERROR,
    EVENT_OPERATION,
    EventEntry,
    EventLog,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc


class TestEventLogRecording:
    def test_record_returns_entry_and_stores_it(self) -> None:
        log = EventLog()
        entry = log.record(EVENT_ERROR, "engine", payload={"m": 1})
        assert isinstance(entry, EventEntry)
        assert entry.event_type == EVENT_ERROR
        assert log.total() == 1
        assert log.entries(EVENT_ERROR)[0] is entry

    def test_entries_filtered_by_type(self) -> None:
        log = EventLog()
        log.record(EVENT_ERROR, "engine")
        log.record(EVENT_OPERATION, "engine")
        assert len(log.entries(EVENT_ERROR)) == 1
        assert len(log.entries(EVENT_OPERATION)) == 1
        assert len(log.entries()) == 2

    def test_maxlen_evicts_oldest(self) -> None:
        log = EventLog(maxlen=3)
        for index in range(5):
            log.record(EVENT_ERROR, f"src-{index}")
        assert log.total() == 3
        sources = [e.source for e in log.entries()]
        assert sources == ["src-2", "src-3", "src-4"]

    def test_maxlen_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            EventLog(maxlen=0)

    def test_clear_removes_everything(self) -> None:
        log = EventLog()
        log.record(EVENT_ERROR, "engine")
        log.clear()
        assert log.total() == 0


class TestEventLogWindows:
    def test_count_in_window_counts_only_recent(self) -> None:
        log = EventLog()
        now = datetime(2026, 8, 3, 12, 0, 0, tzinfo=_UTC)
        log.record(EVENT_ERROR, "engine", at=now - timedelta(seconds=50))
        log.record(EVENT_ERROR, "engine", at=now - timedelta(seconds=100))
        assert log.count_in_window(EVENT_ERROR, 60, now=now) == 1
        assert log.count_in_window(EVENT_ERROR, 120, now=now) == 2

    def test_has_recent(self) -> None:
        log = EventLog()
        now = datetime(2026, 8, 3, 12, 0, 0, tzinfo=_UTC)
        log.record(EVENT_ERROR, "engine", at=now - timedelta(seconds=30))
        assert log.has_recent(EVENT_ERROR, 60, now=now) is True
        assert log.has_recent(EVENT_OPERATION, 60, now=now) is False

    def test_count_since_naive_cutoff(self) -> None:
        """Naive timestamps are interpreted as UTC, matching the recorders."""
        log = EventLog()
        log.record(EVENT_ERROR, "engine", at=datetime(2026, 8, 3, 12, 0, 0))
        count = log.count_since(EVENT_ERROR, since=datetime(2026, 8, 3, 11, 59, 59))
        assert count == 1

    def test_latest_returns_most_recent(self) -> None:
        log = EventLog()
        log.record(EVENT_ERROR, "first", at=datetime(2026, 8, 3, 12, 0, 0, tzinfo=_UTC))
        log.record(EVENT_ERROR, "second", at=datetime(2026, 8, 3, 13, 0, 0, tzinfo=_UTC))
        latest = log.latest(EVENT_ERROR)
        assert latest is not None
        assert latest.source == "second"

    def test_latest_missing_type_returns_none(self) -> None:
        log = EventLog()
        assert log.latest(EVENT_ERROR) is None
