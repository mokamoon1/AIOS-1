"""Paper trading repository tests (AIOS-606, AIOS-407, AIOS-101 section 4.6)."""

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
from aios.database.exceptions import RecordNotFoundError
from aios.database.repositories import (
    BrokerAccountRepository,
    PaperFillRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_BASE = datetime(2026, 8, 1, 12, 0, tzinfo=_UTC)


def _order(
    order_id: str = "ord-1",
    *,
    side: OrderSide = OrderSide.BUY,
    status: OrderStatus = OrderStatus.PENDING,
) -> PaperOrder:
    return PaperOrder(
        order_id=order_id,
        broker_id="bkr-1",
        symbol="AAPL",
        exchange="NASDAQ",
        side=side,
        quantity=10.0,
        price=100.0,
        status=status,
        reason="",
        decision_ref="AAPL:2026-08-01T12:00:00+00:00",
        submitted_at=_BASE,
        updated_at=_BASE,
    )


def _fill(order_id: str = "ord-1", *, realized_pnl: float = 0.0) -> PaperFill:
    return PaperFill(
        fill_id=f"fill-{order_id}",
        order_id=order_id,
        broker_id="bkr-1",
        symbol="AAPL",
        exchange="NASDAQ",
        side=OrderSide.BUY,
        quantity=10.0,
        price=100.0,
        realized_pnl=realized_pnl,
        filled_at=_BASE,
    )


def _position(*, quantity: float = 10.0, current_price: float = 100.0) -> BrokerPosition:
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


def _account(*, cash: float = 99_000.0) -> BrokerAccount:
    return BrokerAccount(
        broker_id="bkr-1",
        account_id="acc-1",
        currency="USD",
        cash=cash,
        initial_cash=100_000.0,
        updated_at=_BASE,
    )


class TestPaperOrderRepository:
    def test_add_and_get(self, session_factory) -> None:
        repo = PaperOrderRepository(session_factory)
        repo.add_order(_order())
        got = repo.get_order("ord-1")
        assert got.symbol == "AAPL"
        assert got.side is OrderSide.BUY
        assert got.status is OrderStatus.PENDING
        assert got.decision_ref == "AAPL:2026-08-01T12:00:00+00:00"

    def test_get_unknown_order_raises(self, session_factory) -> None:
        repo = PaperOrderRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.get_order("missing")

    def test_update_applies_lifecycle_transition(self, session_factory) -> None:
        repo = PaperOrderRepository(session_factory)
        repo.add_order(_order())
        filled = _order(status=OrderStatus.FILLED)
        filled = filled.model_copy(update={"updated_at": _BASE})
        repo.update_order(filled)
        assert repo.get_order("ord-1").status is OrderStatus.FILLED

    def test_update_unknown_order_raises(self, session_factory) -> None:
        repo = PaperOrderRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.update_order(_order())

    def test_list_filters_by_status(self, session_factory) -> None:
        repo = PaperOrderRepository(session_factory)
        repo.add_order(_order(order_id="ord-1"))
        repo.add_order(_order(order_id="ord-2", status=OrderStatus.CANCELLED))
        pending = repo.list_orders(status=OrderStatus.PENDING)
        cancelled = repo.list_orders(status=OrderStatus.CANCELLED)
        assert [order.order_id for order in pending] == ["ord-1"]
        assert [order.order_id for order in cancelled] == ["ord-2"]
        assert len(repo.list_orders()) == 2


class TestPaperFillRepository:
    def test_add_and_list(self, session_factory) -> None:
        repo = PaperFillRepository(session_factory)
        repo.add_fill(_fill())
        repo.add_fill(_fill(order_id="ord-2", realized_pnl=50.0))
        fills = repo.list_fills()
        assert len(fills) == 2
        assert fills[1].order_id == "ord-2"
        assert fills[1].realized_pnl == 50.0

    def test_list_filters_by_order_id(self, session_factory) -> None:
        repo = PaperFillRepository(session_factory)
        repo.add_fill(_fill(order_id="ord-1"))
        repo.add_fill(_fill(order_id="ord-2"))
        assert [fill.order_id for fill in repo.list_fills(order_id="ord-1")] == ["ord-1"]


class TestPaperPositionRepository:
    def test_upsert_and_list(self, session_factory) -> None:
        repo = PaperPositionRepository(session_factory)
        repo.upsert_position(_position())
        positions = repo.list_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 10.0
        assert positions[0].market_value == 1000.0

    def test_upsert_updates_existing_position(self, session_factory) -> None:
        repo = PaperPositionRepository(session_factory)
        repo.upsert_position(_position())
        repo.upsert_position(_position(quantity=6.0, current_price=110.0))
        positions = repo.list_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 6.0
        assert positions[0].current_price == 110.0
        assert positions[0].unrealized_pnl == 60.0

    def test_same_symbol_different_exchange_are_distinct(self, session_factory) -> None:
        repo = PaperPositionRepository(session_factory)
        repo.upsert_position(_position())
        from aios.brokers.models import BrokerPosition

        repo.upsert_position(
            BrokerPosition(
                symbol="AAPL",
                exchange="NYSE",
                quantity=5.0,
                entry_price=100.0,
                current_price=100.0,
                market_value=500.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                updated_at=_BASE,
            )
        )
        assert len(repo.list_positions()) == 2


class TestBrokerAccountRepository:
    def test_upsert_and_get(self, session_factory) -> None:
        repo = BrokerAccountRepository(session_factory)
        repo.upsert_account(_account())
        got = repo.get_account("bkr-1")
        assert got.account_id == "acc-1"
        assert got.cash == 99_000.0
        assert got.initial_cash == 100_000.0

    def test_upsert_updates_existing_account(self, session_factory) -> None:
        repo = BrokerAccountRepository(session_factory)
        repo.upsert_account(_account())
        repo.upsert_account(_account(cash=98_000.0))
        assert repo.get_account("bkr-1").cash == 98_000.0

    def test_get_unknown_account_raises(self, session_factory) -> None:
        repo = BrokerAccountRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.get_account("missing")
