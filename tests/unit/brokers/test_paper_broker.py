"""PaperBroker lifecycle tests (AIOS-407 section 4.3, AIOS-1103 section 11)."""

from __future__ import annotations

import pytest

from aios.brokers.exceptions import (
    BrokerValidationError,
    InvalidOrderStateError,
    OrderAlreadyExistsError,
    OrderNotFoundError,
)
from aios.brokers.models import OrderSide, OrderStatus, PaperOrder
from aios.brokers.paper import DEFAULT_PAPER_INITIAL_CASH, PaperBroker

pytestmark = pytest.mark.unit


def _order(
    broker: PaperBroker,
    *,
    symbol: str = "AAPL",
    exchange: str = "NASDAQ",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 10.0,
    price: float = 100.0,
    order_id: str | None = None,
) -> PaperOrder:
    return PaperOrder(
        order_id=order_id or "ord-1",
        broker_id=broker.broker_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=price,
    )


class TestPaperBroker:
    def test_default_initial_cash_is_documented_placeholder(self) -> None:
        assert DEFAULT_PAPER_INITIAL_CASH == 100_000.0

    def test_check_account_reports_initial_cash(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        account = broker.check_account()
        assert account.broker_id == "bkr-1"
        assert account.account_id == "acc-1"
        assert account.currency == "USD"
        assert account.cash == DEFAULT_PAPER_INITIAL_CASH
        assert account.initial_cash == DEFAULT_PAPER_INITIAL_CASH

    def test_submit_returns_pending_order(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        submitted = broker.submit_order(_order(broker))
        assert submitted.status is OrderStatus.PENDING
        assert broker.get_order("ord-1").status is OrderStatus.PENDING

    def test_submit_duplicate_order_id_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        with pytest.raises(OrderAlreadyExistsError):
            broker.submit_order(_order(broker))

    def test_submit_foreign_broker_order_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        foreign = PaperOrder(
            order_id="ord-x",
            broker_id="bkr-other",
            symbol="AAPL",
            exchange="NASDAQ",
            side=OrderSide.BUY,
            quantity=1.0,
            price=100.0,
        )
        with pytest.raises(BrokerValidationError):
            broker.submit_order(foreign)

    def test_submit_does_not_fill_or_consume_cash(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        assert broker.check_account().cash == DEFAULT_PAPER_INITIAL_CASH
        assert broker.get_positions() == []

    def test_fill_buy_consumes_cash_and_opens_position(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker, quantity=10.0, price=100.0))
        filled, fill = broker.fill_order("ord-1", price=100.0)
        assert filled.status is OrderStatus.FILLED
        assert fill.order_id == "ord-1"
        assert fill.price == 100.0
        assert fill.realized_pnl == 0.0
        assert broker.check_account().cash == DEFAULT_PAPER_INITIAL_CASH - 1000.0
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10.0
        assert positions[0].entry_price == 100.0
        assert positions[0].realized_pnl == 0.0

    def test_fill_buy_insufficient_cash_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker, quantity=2000.0, price=100.0))
        with pytest.raises(BrokerValidationError):
            broker.fill_order("ord-1", price=100.0)
        assert broker.get_order("ord-1").status is OrderStatus.PENDING

    def test_fill_buy_averages_entry_price(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker, quantity=10.0, price=100.0))
        broker.fill_order("ord-1", price=100.0)
        broker.submit_order(_order(broker, order_id="ord-2", quantity=10.0, price=120.0))
        broker.fill_order("ord-2", price=120.0)
        position = broker.get_positions()[0]
        assert position.quantity == 20.0
        assert position.entry_price == 110.0

    def test_fill_sell_realizes_pnl_and_closes_position(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker, quantity=10.0, price=100.0))
        broker.fill_order("ord-1", price=100.0)
        broker.submit_order(
            _order(
                broker,
                order_id="ord-2",
                side=OrderSide.SELL,
                quantity=10.0,
                price=120.0,
            )
        )
        filled, fill = broker.fill_order("ord-2", price=120.0)
        assert filled.status is OrderStatus.FILLED
        assert fill.realized_pnl == 200.0
        assert broker.get_positions() == []
        status = broker.get_portfolio_status()
        assert status.realized_pnl == 200.0
        assert status.cash == DEFAULT_PAPER_INITIAL_CASH + 200.0

    def test_fill_sell_partial_reduces_position(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker, quantity=10.0, price=100.0))
        broker.fill_order("ord-1", price=100.0)
        broker.submit_order(
            _order(
                broker,
                order_id="ord-2",
                side=OrderSide.SELL,
                quantity=4.0,
                price=110.0,
            )
        )
        broker.fill_order("ord-2", price=110.0)
        position = broker.get_positions()[0]
        assert position.quantity == 6.0
        assert position.realized_pnl == 40.0

    def test_fill_sell_insufficient_position_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker, quantity=10.0, price=100.0))
        broker.fill_order("ord-1", price=100.0)
        broker.submit_order(
            _order(
                broker,
                order_id="ord-2",
                side=OrderSide.SELL,
                quantity=20.0,
                price=110.0,
            )
        )
        with pytest.raises(BrokerValidationError):
            broker.fill_order("ord-2", price=110.0)

    def test_fill_sell_without_position_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker, side=OrderSide.SELL))
        with pytest.raises(BrokerValidationError):
            broker.fill_order("ord-1", price=100.0)

    def test_fill_with_non_positive_price_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        with pytest.raises(BrokerValidationError):
            broker.fill_order("ord-1", price=0.0)

    def test_cancel_pending_order(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        cancelled = broker.cancel_order("ord-1")
        assert cancelled.status is OrderStatus.CANCELLED
        assert broker.get_order("ord-1").status is OrderStatus.CANCELLED

    def test_reject_pending_order_records_reason(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        rejected = broker.reject_order("ord-1", reason="policy hold")
        assert rejected.status is OrderStatus.REJECTED
        assert rejected.reason == "policy hold"

    def test_reject_without_reason_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        with pytest.raises(BrokerValidationError):
            broker.reject_order("ord-1", reason="  ")

    @pytest.mark.parametrize(
        "lifecycle",
        ["fill", "cancel", "reject"],
    )
    def test_non_pending_order_cannot_change_state(self, lifecycle: str) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        broker.cancel_order("ord-1")
        with pytest.raises(InvalidOrderStateError):
            if lifecycle == "fill":
                broker.fill_order("ord-1", price=100.0)
            elif lifecycle == "cancel":
                broker.cancel_order("ord-1")
            else:
                broker.reject_order("ord-1", reason="nope")

    def test_get_unknown_order_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        with pytest.raises(OrderNotFoundError):
            broker.get_order("missing")

    def test_cancel_unknown_order_raises(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        with pytest.raises(OrderNotFoundError):
            broker.cancel_order("missing")

    def test_list_orders_in_submission_order(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        broker.submit_order(_order(broker))
        broker.submit_order(_order(broker, order_id="ord-2"))
        assert [order.order_id for order in broker.list_orders()] == ["ord-1", "ord-2"]

    def test_portfolio_status_math(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1", initial_cash=1000.0)
        broker.submit_order(_order(broker, quantity=5.0, price=100.0))
        broker.fill_order("ord-1", price=100.0)
        status = broker.get_portfolio_status()
        assert status.cash == 500.0
        assert status.market_value == 500.0
        assert status.equity == 1000.0
        assert status.position_count == 1
        assert status.realized_pnl == 0.0

    def test_update_current_prices_requires_positive_prices(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        with pytest.raises(BrokerValidationError):
            broker.update_current_prices({"AAPL": 0.0})

    def test_current_price_from_market_returns_latest_close(self) -> None:
        from datetime import datetime, timezone

        from aios.data.models import Candle, Timeframe

        broker = PaperBroker("bkr-1", "acc-1")
        base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        candles = [
            Candle(
                symbol="AAPL",
                timeframe=Timeframe.ONE_HOUR,
                timestamp=base,
                open=1,
                high=2,
                low=1,
                close=10,
                volume=1,
            ),
            Candle(
                symbol="AAPL",
                timeframe=Timeframe.ONE_HOUR,
                timestamp=base,
                open=1,
                high=2,
                low=1,
                close=20,
                volume=1,
            ),
            Candle(
                symbol="MSFT",
                timeframe=Timeframe.ONE_HOUR,
                timestamp=base,
                open=1,
                high=2,
                low=1,
                close=5,
                volume=1,
            ),
        ]
        assert broker.current_price_from_market(candles, "AAPL") == 20.0
        assert broker.current_price_from_market(candles, "NOPE") is None
