"""Performance Tracking service tests (AIOS-308 section 12)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
)
from aios.performance.exceptions import PerformanceError
from aios.performance.service import PerformanceDataReader, PerformanceService

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_BASE = datetime(2026, 8, 1, 12, 0, tzinfo=_UTC)


def _account(*, cash: float = 50_000.0, initial_cash: float = 100_000.0) -> BrokerAccount:
    return BrokerAccount(
        broker_id="bkr-1",
        account_id="acc-1",
        currency="USD",
        cash=cash,
        initial_cash=initial_cash,
        updated_at=_BASE,
    )


def _fill(price: float = 100.0, *, realized_pnl: float = 0.0) -> PaperFill:
    return PaperFill(
        fill_id=f"fill-{price}-{realized_pnl}",
        order_id="ord-1",
        broker_id="bkr-1",
        symbol="AAPL",
        exchange="NASDAQ",
        side=OrderSide.SELL,
        quantity=10.0,
        price=price,
        realized_pnl=realized_pnl,
        filled_at=_BASE,
    )


def _order(order_id: str = "ord-1") -> PaperOrder:
    return PaperOrder(
        order_id=order_id,
        broker_id="bkr-1",
        symbol="AAPL",
        exchange="NASDAQ",
        side=OrderSide.BUY,
        quantity=10.0,
        price=100.0,
        submitted_at=_BASE,
        updated_at=_BASE,
    )


def _position(*, quantity: float = 10.0, current_price: float = 110.0) -> BrokerPosition:
    return BrokerPosition(
        symbol="AAPL",
        exchange="NASDAQ",
        quantity=quantity,
        entry_price=100.0,
        current_price=current_price,
        market_value=current_price * quantity,
        unrealized_pnl=(current_price - 100.0) * quantity,
        realized_pnl=0.0,
        updated_at=_BASE,
    )


class TestPerformanceService:
    def test_build_snapshot_empty_portfolio(self) -> None:
        service = PerformanceService()
        snapshot = service.build_snapshot(
            account=_account(),
            orders=[],
            fills=[],
            positions=[],
        )
        assert snapshot.broker_id == "bkr-1"
        assert snapshot.equity == 50_000.0
        assert snapshot.market_value == 0.0
        assert snapshot.realized_pnl == 0.0
        assert snapshot.unrealized_pnl == 0.0
        assert snapshot.total_pnl == 0.0
        assert snapshot.total_return_pct == 0.0
        assert snapshot.order_count == 0
        assert snapshot.fill_count == 0
        assert snapshot.position_count == 0

    def test_build_snapshot_with_realized_and_unrealized_pnl(self) -> None:
        service = PerformanceService()
        snapshot = service.build_snapshot(
            account=_account(cash=50_000.0),
            orders=[_order(), _order(order_id="ord-2")],
            fills=[_fill(realized_pnl=200.0), _fill(price=150.0, realized_pnl=50.0)],
            positions=[_position()],
        )
        assert snapshot.order_count == 2
        assert snapshot.fill_count == 2
        assert snapshot.realized_pnl == 250.0
        assert snapshot.unrealized_pnl == 100.0
        assert snapshot.total_pnl == 350.0
        assert snapshot.market_value == 1100.0
        assert snapshot.equity == 51_100.0
        assert snapshot.total_return_pct == pytest.approx(0.35)
        assert snapshot.position_count == 1
        assert snapshot.positions[0].symbol == "AAPL"

    def test_total_return_uses_initial_cash(self) -> None:
        service = PerformanceService()
        snapshot = service.build_snapshot(
            account=_account(initial_cash=50_000.0, cash=55_000.0),
            orders=[_order()],
            fills=[_fill(realized_pnl=500.0)],
            positions=[],
        )
        assert snapshot.total_return_pct == 1.0

    def test_current_snapshot_requires_reader(self) -> None:
        service = PerformanceService()
        with pytest.raises(PerformanceError):
            service.current_snapshot("bkr-1")

    def test_current_snapshot_reads_from_reader(self) -> None:
        class _Reader(PerformanceDataReader):
            def get_broker_account(self, broker_id: str) -> BrokerAccount:
                return _account()

            def list_paper_orders(self, *, status: OrderStatus | None = None) -> list[PaperOrder]:
                return [_order()]

            def list_paper_fills(self, *, order_id: str | None = None) -> list[PaperFill]:
                return [_fill(realized_pnl=50.0)]

            def list_paper_positions(self) -> list[BrokerPosition]:
                return [_position()]

        service = PerformanceService(reader=_Reader())
        snapshot = service.current_snapshot("bkr-1")
        assert snapshot.order_count == 1
        assert snapshot.fill_count == 1
        assert snapshot.realized_pnl == 50.0
        assert snapshot.unrealized_pnl == 100.0
        assert snapshot.position_count == 1
