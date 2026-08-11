"""Market session guard tests (Phase 9.6, P0-5)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from aios.brokers.market_session import MarketSessionGuard

pytestmark = pytest.mark.unit

_UTC = timezone.utc

# Thursday 2026-08-06 is a trading weekday; 2026-08-08 is Saturday,
# 2026-08-09 is Sunday.


def _moment(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=_UTC)


class TestMarketSessionGuard:
    def test_open_during_session_hours(self) -> None:
        guard = MarketSessionGuard()
        # 2026-08-06 10:00 UTC is 06:00 in America/New_York (pre-open in EDT
        # which is UTC-4), so use a time that lands inside 09:30-16:00 EDT.
        at = _moment(2026, 8, 6, 14, 0)  # 10:00 EDT
        assert guard.is_open(at) is True
        assert guard.closed_reason(at) is None

    def test_closed_after_close(self) -> None:
        guard = MarketSessionGuard()
        at = _moment(2026, 8, 6, 20, 0)  # 16:00 EDT
        assert guard.is_open(at) is False
        assert "close" in (guard.closed_reason(at) or "")

    def test_closed_before_open(self) -> None:
        guard = MarketSessionGuard()
        at = _moment(2026, 8, 6, 12, 0)  # 08:00 EDT
        assert guard.is_open(at) is False
        assert "before open" in (guard.closed_reason(at) or "")

    def test_closed_on_saturday(self) -> None:
        guard = MarketSessionGuard()
        at = _moment(2026, 8, 8, 14, 0)
        assert guard.is_open(at) is False
        assert "weekend" in (guard.closed_reason(at) or "")

    def test_closed_on_sunday(self) -> None:
        guard = MarketSessionGuard()
        at = _moment(2026, 8, 9, 14, 0)
        assert guard.is_open(at) is False

    def test_closed_on_configured_holiday(self) -> None:
        guard = MarketSessionGuard(holidays={date(2026, 8, 6)})
        at = _moment(2026, 8, 6, 14, 0)
        assert guard.is_open(at) is False
        assert "holiday" in (guard.closed_reason(at) or "")

    def test_disabled_guard_always_open(self) -> None:
        guard = MarketSessionGuard(enabled=False)
        assert guard.is_open(_moment(2026, 8, 8, 14, 0)) is True
        assert guard.closed_reason(_moment(2026, 8, 8, 14, 0)) is None

    def test_injected_clock_drives_is_open(self) -> None:
        clock = lambda: _moment(2026, 8, 8, 14, 0)  # noqa: E731
        guard = MarketSessionGuard(now_fn=clock)
        assert guard.is_open() is False
        # Naive injected clock is interpreted as UTC.
        clock_naive = lambda: datetime(2026, 8, 6, 14, 0)  # noqa: E731
        guard_naive = MarketSessionGuard(now_fn=clock_naive)
        assert guard_naive.is_open() is True

    def test_custom_window_bounds(self) -> None:
        guard = MarketSessionGuard(open_time="08:00", close_time="12:00")
        # 2026-08-06 11:00 UTC is 07:00 EDT -> before open.
        assert guard.is_open(_moment(2026, 8, 6, 11, 0)) is False
        # 2026-08-06 15:00 UTC is 11:00 EDT -> inside window.
        assert guard.is_open(_moment(2026, 8, 6, 15, 0)) is True

    def test_invalid_time_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketSessionGuard(open_time="not-a-time")

    def test_from_settings_uses_config(self) -> None:
        class _Trading:
            market_session_enabled = True
            market_timezone = "America/New_York"
            market_open = "09:30"
            market_close = "16:00"
            market_holidays = ["2026-08-06"]

        guard = MarketSessionGuard.from_settings(_Trading())
        assert guard.holidays == frozenset({date(2026, 8, 6)})
        assert guard.is_open(_moment(2026, 8, 6, 14, 0)) is False


class TestSessionGuardAdapter:
    def test_adapter_reports_closed_reason(self) -> None:
        from aios.brokers.guards import MarketSessionGuardAdapter

        guard = MarketSessionGuard(now_fn=lambda: _moment(2026, 8, 8, 14, 0))
        adapter = MarketSessionGuardAdapter(guard)
        assert "weekend" in adapter.block_reason(object())

    def test_adapter_allows_when_open(self) -> None:
        from aios.brokers.guards import MarketSessionGuardAdapter

        guard = MarketSessionGuard(now_fn=lambda: _moment(2026, 8, 6, 14, 0))
        adapter = MarketSessionGuardAdapter(guard)
        assert adapter.block_reason(object()) is None
