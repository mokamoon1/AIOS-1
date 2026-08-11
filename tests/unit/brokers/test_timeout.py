"""Pending-order timeout monitor tests (Phase 9.6, P0-3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.brokers.models import OrderSide, OrderStatus, PaperOrder
from aios.brokers.timeout import PendingOrderTimeoutMonitor
from aios.monitoring.event_log import EVENT_ORDER_TIMEOUT, EventLog

pytestmark = pytest.mark.unit

_UTC = timezone.utc

_NOW = datetime(2026, 8, 3, 12, 0, 0, tzinfo=_UTC)


def _order(
    order_id: str,
    *,
    status: OrderStatus = OrderStatus.PENDING,
    age_seconds: int = 0,
    symbol: str = "AAPL",
) -> PaperOrder:
    return PaperOrder(
        order_id=order_id,
        broker_id="bkr-1",
        symbol=symbol,
        exchange="NASDAQ",
        side=OrderSide.BUY,
        quantity=10.0,
        price=100.0,
        status=status,
        updated_at=_NOW - timedelta(seconds=age_seconds),
    )


class _RecordingBroker:
    """Broker spy recording cancellation calls."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.fail_on: set[str] = set()

    def list_orders(self) -> list[PaperOrder]:
        return []

    def cancel_order(self, order_id: str) -> PaperOrder:
        if order_id in self.fail_on:
            raise RuntimeError(f"cannot cancel {order_id}")
        self.cancelled.append(order_id)
        return _order(order_id, status=OrderStatus.CANCELLED, age_seconds=999)


class TestPendingOrderTimeoutMonitor:
    def test_identity_from_settings(self) -> None:
        class _Trading:
            pending_order_timeout_seconds = 600
            order_timeout_scan_interval_seconds = 45

        # Config surface is validated via TradingSettings in config tests; here
        # we just confirm the monitor takes its timeout from a simple value.
        monitor = PendingOrderTimeoutMonitor(_RecordingBroker(), timeout_seconds=600)
        assert monitor.timeout_seconds == 600

    def test_expired_pending_identified(self) -> None:
        monitor = PendingOrderTimeoutMonitor(_RecordingBroker(), timeout_seconds=300)
        orders = [
            _order("old", age_seconds=301),
            _order("recent", age_seconds=299),
            _order("filled", status=OrderStatus.FILLED, age_seconds=999),
            _order("cancelled", status=OrderStatus.CANCELLED, age_seconds=999),
            _order("rejected", status=OrderStatus.REJECTED, age_seconds=999),
        ]
        expired = monitor.expired_pending(orders, now=_NOW)
        assert [o.order_id for o in expired] == ["old"]

    def test_cancel_expired_cancels_and_records_events(self) -> None:
        broker = _RecordingBroker()
        log = EventLog()
        monitor = PendingOrderTimeoutMonitor(broker, timeout_seconds=300, event_log=log)
        cancelled = monitor.cancel_expired(
            [_order("old", age_seconds=400)], now=_NOW
        )
        assert broker.cancelled == ["old"]
        assert [o.order_id for o in cancelled] == ["old"]
        assert log.count_in_window(EVENT_ORDER_TIMEOUT, 60, now=_NOW) == 1
        entry = log.latest(EVENT_ORDER_TIMEOUT)
        assert entry.payload["order_id"] == "old"
        assert entry.payload["status_after"] == "cancelled"
        assert entry.payload["timeout_seconds"] == 300

    def test_recent_pending_not_cancelled(self) -> None:
        broker = _RecordingBroker()
        monitor = PendingOrderTimeoutMonitor(broker, timeout_seconds=300)
        monitor.cancel_expired([_order("fresh", age_seconds=30)], now=_NOW)
        assert broker.cancelled == []

    def test_non_pending_orders_never_touched(self) -> None:
        broker = _RecordingBroker()
        monitor = PendingOrderTimeoutMonitor(broker, timeout_seconds=300)
        orders = [
            _order("filled", status=OrderStatus.FILLED, age_seconds=5000),
            _order("cancelled", status=OrderStatus.CANCELLED, age_seconds=5000),
            _order("rejected", status=OrderStatus.REJECTED, age_seconds=5000),
        ]
        monitor.cancel_expired(orders, now=_NOW)
        assert broker.cancelled == []
        assert monitor.expired_pending(orders, now=_NOW) == []

    def test_cancel_failure_is_logged_and_skipped(self) -> None:
        broker = _RecordingBroker()
        broker.fail_on.add("failing")
        monitor = PendingOrderTimeoutMonitor(broker, timeout_seconds=300, event_log=EventLog())
        cancelled = monitor.cancel_expired(
            [_order("failing", age_seconds=400), _order("ok", age_seconds=400)],
            now=_NOW,
        )
        assert [o.order_id for o in cancelled] == ["ok"]
        assert broker.cancelled == ["ok"]

    def test_injected_clock_drives_expiration(self) -> None:
        broker = _RecordingBroker()
        monitor = PendingOrderTimeoutMonitor(
            broker, timeout_seconds=300, now_fn=lambda: _NOW
        )
        monitor.cancel_expired([_order("old", age_seconds=301)])
        assert broker.cancelled == ["old"]

    def test_invalid_timeout_rejected(self) -> None:
        with pytest.raises(ValueError):
            PendingOrderTimeoutMonitor(_RecordingBroker(), timeout_seconds=0)


class TestTimeoutOnBrokerService:
    def test_engine_monitor_cancels_expired_pending_order(self) -> None:
        """Full path: broker order ages past the timeout and is auto-cancelled."""
        from aios.brokers.paper import PaperBroker

        broker = PaperBroker("bkr-1", "acc-1")
        now = datetime(2026, 8, 3, 12, 0, 0, tzinfo=_UTC)
        order = _order("ord-timeout-1", age_seconds=600)
        broker.submit_order(order)
        assert broker.get_order("ord-timeout-1").status is OrderStatus.PENDING

        log = EventLog()
        monitor = PendingOrderTimeoutMonitor(broker, timeout_seconds=300, event_log=log)
        cancelled = monitor.cancel_expired(broker.list_orders(), now=now)
        assert [o.order_id for o in cancelled] == ["ord-timeout-1"]
        assert broker.get_order("ord-timeout-1").status is OrderStatus.CANCELLED
        assert log.count_in_window(EVENT_ORDER_TIMEOUT, 60, now=now) == 1
