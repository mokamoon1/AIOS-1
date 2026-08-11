"""Pending-order timeout monitor (Phase 9.6, P0-3).

Detects PENDING paper orders older than the configured timeout and cancels
them safely. Only PENDING orders are touched: FILLED, CANCELLED, and REJECTED
orders are never affected (AIOS-1103 section 11 lifecycle). Each auto-cancel
is recorded as an ``ORDER_TIMEOUT`` audit event so the action is traceable.

The clock is injected (``now_fn``) so expiration logic is deterministic and
testable without waiting for real time.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from aios.brokers.models import OrderStatus, PaperOrder
from aios.monitoring.event_log import EVENT_ORDER_TIMEOUT, EventLog

_Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


class PendingOrderTimeoutMonitor:
    """Scans for expired PENDING orders and auto-cancels them.

    ``broker`` is a broker-like object with ``list_orders()`` and
    ``cancel_order(order_id)``. ``cancel`` performs the actual cancellation
    so tests can substitute a spy and the timeout logic stays observable.
    """

    def __init__(
        self,
        broker: Any,
        *,
        timeout_seconds: int = 300,
        event_log: EventLog | None = None,
        now_fn: _Clock | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        self._broker = broker
        self._timeout_seconds = timeout_seconds
        self._event_log = event_log or EventLog()
        self._now_fn = now_fn or _system_clock
        self._logger = logger or logging.getLogger("aios.brokers.timeout")

    @property
    def timeout_seconds(self) -> int:
        """Return the configured PENDING timeout in seconds."""
        return self._timeout_seconds

    def expired_pending(self, orders: Sequence[PaperOrder], now: datetime | None = None) -> list[PaperOrder]:
        """Return PENDING orders whose age exceeds the timeout at ``now``."""
        reference = now or self._now_fn()
        cutoff = reference - timedelta(seconds=self._timeout_seconds)
        expired: list[PaperOrder] = []
        for order in orders:
            if order.status is not OrderStatus.PENDING:
                continue
            if order.updated_at <= cutoff:
                expired.append(order)
        return expired

    def cancel_expired(self, orders: Sequence[PaperOrder], now: datetime | None = None) -> list[PaperOrder]:
        """Cancel all expired PENDING orders and record an audit event each.

        Returns the cancelled orders. A cancellation that raises (for example
        an order that was concurrently transitioned away from PENDING) is
        logged and skipped, never silently swallowed as a timeout success.
        """
        reference = now or self._now_fn()
        cancelled: list[PaperOrder] = []
        for order in self.expired_pending(orders, now=reference):
            try:
                updated = self._broker.cancel_order(order.order_id)
            except Exception as exc:  # noqa: BLE001 - guard, log, continue
                self._logger.warning(
                    "Could not auto-cancel expired order %s: %s", order.order_id, exc
                )
                continue
            cancelled.append(updated)
            self._event_log.record(
                EVENT_ORDER_TIMEOUT,
                "broker.timeout_monitor",
                payload={
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "status_after": updated.status.value,
                    "timeout_seconds": self._timeout_seconds,
                },
                at=reference,
            )
            self._logger.info(
                "Auto-cancelled expired PENDING order %s (%s) after %ds",
                order.order_id,
                order.symbol,
                self._timeout_seconds,
            )
        return cancelled
