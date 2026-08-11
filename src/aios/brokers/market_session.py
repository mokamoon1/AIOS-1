"""Market session guard (Phase 9.6, P0-5).

Blocks order submission/execution when the market is closed: weekends,
configured holidays, and times outside the configured session hours. The
clock is injected (``now_fn``) so behavior is deterministic and testable;
the default reads the system clock.

The session window is interpreted in the configured exchange timezone
(default ``America/New_York``), never in the machine-local timezone, so
results do not depend on where the process runs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

_TIMEZONE = ZoneInfo("America/New_York")

_Clocker = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SessionWindow:
    """A configured market session window."""

    open_time: time
    close_time: time
    timezone_name: str = "America/New_York"

    def timezone(self) -> Any:
        try:
            return ZoneInfo(self.timezone_name)
        except Exception:
            return _TIMEZONE


def _parse_time(value: str, field_name: str) -> time:
    try:
        hour, minute = value.strip().split(":")
        return time(int(hour), int(minute))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be HH:MM, got {value!r}") from exc


class MarketSessionGuard:
    """Deterministic market-session gate for order execution.

    ``is_open`` returns True only when the evaluated instant falls on a
    trading weekday (Monday-Friday), is not a configured holiday, and lies
    within ``[open_time, close_time)`` in the exchange timezone.
    """

    def __init__(
        self,
        *,
        open_time: str = "09:30",
        close_time: str = "16:00",
        timezone_name: str = "America/New_York",
        holidays: set[date] | None = None,
        enabled: bool = True,
        now_fn: _Clocker | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._window = SessionWindow(
            open_time=_parse_time(open_time, "market_open"),
            close_time=_parse_time(close_time, "market_close"),
            timezone_name=timezone_name,
        )
        self._holidays = set(holidays or ())
        self._enabled = enabled
        self._now_fn = now_fn or _system_clock
        self._logger = logger or logging.getLogger("aios.brokers.market_session")

    @classmethod
    def from_settings(
        cls,
        trading: Any,
        *,
        logger: logging.Logger | None = None,
        now_fn: _Clocker | None = None,
    ) -> "MarketSessionGuard":
        """Build a guard from :class:`TradingSettings` (config-driven)."""
        holidays: set[date] = set()
        for raw in getattr(trading, "market_holidays", []) or []:
            try:
                holidays.add(date.fromisoformat(str(raw)))
            except ValueError:
                logger = logger or logging.getLogger("aios.brokers.market_session")
                logger.warning("Ignoring invalid market holiday %r", raw)
        return cls(
            open_time=getattr(trading, "market_open", "09:30"),
            close_time=getattr(trading, "market_close", "16:00"),
            timezone_name=getattr(trading, "market_timezone", "America/New_York"),
            holidays=holidays,
            enabled=bool(getattr(trading, "market_session_enabled", True)),
            now_fn=now_fn,
            logger=logger,
        )

    @property
    def enabled(self) -> bool:
        """Return whether the guard is active."""
        return self._enabled

    @property
    def holidays(self) -> frozenset[date]:
        """Return the configured market holidays."""
        return frozenset(self._holidays)

    def is_open(self, at: datetime | None = None) -> bool:
        """Return True when the market is open at ``at`` (default: now)."""
        if not self._enabled:
            return True
        moment = self._now_fn() if at is None else at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        exchange_time = moment.astimezone(self._window.timezone())
        if exchange_time.weekday() >= 5:
            return False
        if exchange_time.date() in self._holidays:
            return False
        local_time = exchange_time.time()
        return self._window.open_time <= local_time < self._window.close_time

    def closed_reason(self, at: datetime | None = None) -> str | None:
        """Return why the market is closed at ``at``, or ``None`` when open."""
        if not self._enabled:
            return None
        moment = self._now_fn() if at is None else at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        exchange_time = moment.astimezone(self._window.timezone())
        if exchange_time.weekday() >= 5:
            return f"market closed on weekend ({exchange_time.strftime('%A')})"
        if exchange_time.date() in self._holidays:
            return f"market closed on holiday {exchange_time.date().isoformat()}"
        local_time = exchange_time.time()
        if local_time < self._window.open_time:
            return (
                f"market closed: {exchange_time.strftime('%H:%M')} before open "
                f"{self._window.open_time.isoformat()}"
            )
        if local_time >= self._window.close_time:
            return (
                f"market closed: {exchange_time.strftime('%H:%M')} at/after close "
                f"{self._window.close_time.isoformat()}"
            )
        return None
