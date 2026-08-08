"""Deterministic Paper Trading broker adapter (AIOS-407 section 4.3).

Version 1 is Paper Trading only (AIOS-101 section 4.6, AIOS-208 section 8,
AIOS-603 section 11). The broker holds its account, positions, and order book
in memory and executes only the explicit lifecycle operations. Orders never
auto-fill and no slippage, fee, latency, or position-sizing model is applied
(AIOS-208 section 9).

Lifecycle (AIOS-1103 section 11):

    submit -> PENDING
    PENDING -> FILLED      (explicit ``fill_order``)
    PENDING -> CANCELLED   (explicit ``cancel_order``)
    PENDING -> REJECTED    (explicit ``reject_order``)

All other transitions raise :class:`InvalidOrderStateError`. Fills are
recorded at the requested price; the current price used for position
valuation is the last recorded trade price for the symbol, refreshed only
through the explicit ``update_current_prices`` placeholder.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import final
from uuid import uuid4

from aios.brokers.exceptions import (
    BrokerValidationError,
    InvalidOrderStateError,
    OrderAlreadyExistsError,
    OrderNotFoundError,
)
from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
    PortfolioStatus,
)
from aios.data.models import Candle

DEFAULT_PAPER_INITIAL_CASH = 100_000.0

_PositionKey = tuple[str, str]


@final
class _PositionState:
    """Mutable internal position state used by the paper broker.

    Not part of the public API; converted to the immutable
    :class:`BrokerPosition` model by :meth:`PaperBroker.get_positions`.
    """

    __slots__ = ("symbol", "exchange", "quantity", "entry_price", "realized_pnl", "current_price")

    def __init__(
        self,
        symbol: str,
        exchange: str,
        quantity: float,
        entry_price: float,
        current_price: float,
        realized_pnl: float = 0.0,
    ) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.quantity = quantity
        self.entry_price = entry_price
        self.current_price = current_price
        self.realized_pnl = realized_pnl


class PaperBroker:
    """In-memory Paper Trading broker implementing :class:`BrokerInterface`.

    The initial cash is a configurable placeholder (the approved documents do
    not fix the starting paper balance). ``fill_order`` records a fill at the
    requested price and updates the account, positions, and last trade price;
    ``reject_order`` is the explicit rejection path for policy decisions.
    """

    def __init__(
        self,
        broker_id: str,
        account_id: str,
        initial_cash: float = DEFAULT_PAPER_INITIAL_CASH,
        currency: str = "USD",
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        if initial_cash <= 0:
            raise BrokerValidationError("initial paper cash must be positive")
        self._broker_id = broker_id
        self._account_id = account_id
        self._currency = currency
        self._initial_cash = float(initial_cash)
        self._cash = float(initial_cash)
        self._orders: dict[str, PaperOrder] = {}
        self._fills: list[PaperFill] = []
        self._positions: dict[_PositionKey, _PositionState] = {}
        self._last_prices: dict[_PositionKey, float] = {}
        self._realized_pnl = 0.0
        self._logger = logger or logging.getLogger("aios.brokers.paper")

    # -- identity ----------------------------------------------------------

    @property
    def broker_id(self) -> str:
        """Return the broker identifier (AIOS-1103 ``broker_id``)."""
        return self._broker_id

    @property
    def account_id(self) -> str:
        """Return the account identifier."""
        return self._account_id

    # -- documented operations (AIOS-407 section 4.3) ----------------------

    def check_account(self) -> BrokerAccount:
        """Return the account status (Check Account)."""
        return BrokerAccount(
            broker_id=self._broker_id,
            account_id=self._account_id,
            currency=self._currency,
            cash=self._cash,
            initial_cash=self._initial_cash,
        )

    def submit_order(self, order: PaperOrder) -> PaperOrder:
        """Submit a paper order and return it in the PENDING state.

        Raises :class:`OrderAlreadyExistsError` for a duplicate ``order_id``
        and :class:`BrokerValidationError` when the order does not belong to
        this broker. Feasibility (cash and position availability) is checked
        at fill time, keeping the submit -> PENDING transition unconditional
        for well-formed orders (AIOS-1103 section 11).
        """
        if order.order_id in self._orders:
            raise OrderAlreadyExistsError(f"Order {order.order_id!r} was already submitted")
        if order.broker_id != self._broker_id:
            raise BrokerValidationError(
                f"Order {order.order_id!r} belongs to broker {order.broker_id!r}, "
                f"not {self._broker_id!r}"
            )
        self._orders[order.order_id] = order
        self._logger.info(
            "Paper order %s submitted: %s %s %s x %s",
            order.order_id,
            order.side.value,
            order.symbol,
            order.quantity,
            order.price,
        )
        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        """Cancel a PENDING paper order (PENDING -> CANCELLED)."""
        order = self._require_pending(order_id)
        updated = order.model_copy(
            update={
                "status": OrderStatus.CANCELLED,
                "reason": "cancelled",
                "updated_at": self._now(),
            }
        )
        self._orders[order_id] = updated
        self._logger.info("Paper order %s cancelled", order_id)
        return updated

    def reject_order(self, order_id: str, *, reason: str) -> PaperOrder:
        """Reject a PENDING paper order (PENDING -> REJECTED).

        ``reason`` documents why the order was rejected so execution history
        remains explainable (AIOS-208 section 11).
        """
        if not reason or not reason.strip():
            raise BrokerValidationError("a rejection reason is required")
        order = self._require_pending(order_id)
        updated = order.model_copy(
            update={
                "status": OrderStatus.REJECTED,
                "reason": reason.strip(),
                "updated_at": self._now(),
            }
        )
        self._orders[order_id] = updated
        self._logger.info("Paper order %s rejected: %s", order_id, reason)
        return updated

    def get_order(self, order_id: str) -> PaperOrder:
        """Return the order identified by ``order_id``."""
        return self._get_order(order_id)

    def list_orders(self) -> list[PaperOrder]:
        """Return all submitted orders in submission order."""
        return list(self._orders.values())

    def get_positions(self) -> list[BrokerPosition]:
        """Return the open positions with objective metrics (Get Positions)."""
        now = self._now()
        result: list[BrokerPosition] = []
        for key, state in self._positions.items():
            symbol, exchange = key
            current_price = self._last_prices.get(key, state.entry_price)
            market_value = current_price * state.quantity
            unrealized_pnl = (current_price - state.entry_price) * state.quantity
            result.append(
                BrokerPosition(
                    symbol=symbol,
                    exchange=exchange,
                    quantity=state.quantity,
                    entry_price=state.entry_price,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=state.realized_pnl,
                    updated_at=now,
                )
            )
        result.sort(key=lambda position: (position.symbol, position.exchange))
        return result

    def get_portfolio_status(self) -> PortfolioStatus:
        """Return the portfolio status (Get Portfolio Status, AIOS-407)."""
        positions = self.get_positions()
        market_value = sum(position.market_value for position in positions)
        equity = self._cash + market_value
        return PortfolioStatus(
            broker_id=self._broker_id,
            account_id=self._account_id,
            currency=self._currency,
            cash=self._cash,
            market_value=market_value,
            equity=equity,
            realized_pnl=self._realized_pnl,
            position_count=len(positions),
            positions=positions,
        )

    # -- explicit simulation operations ------------------------------------

    def fill_order(self, order_id: str, *, price: float) -> tuple[PaperOrder, PaperFill]:
        """Fill a PENDING order at ``price`` (PENDING -> FILLED).

        A fill is an explicit, recorded event: the order never auto-fills and
        no slippage is applied. Buy fills consume cash and raise the position
        quantity; sell fills add cash, realize ``(price - entry_price) *
        quantity``, and reduce the position (closing it at zero).
        """
        order = self._require_pending(order_id)
        if not price or price <= 0:
            raise BrokerValidationError("fill price must be positive")
        key = (order.symbol, order.exchange)
        realized_pnl = 0.0
        if order.side is OrderSide.BUY:
            cost = price * order.quantity
            if cost > self._cash:
                raise BrokerValidationError(
                    f"Insufficient paper cash to fill {order_id}: "
                    f"need {cost:.2f}, have {self._cash:.2f}"
                )
            self._cash -= cost
            state = self._positions.get(key)
            if state is None:
                self._positions[key] = _PositionState(
                    order.symbol, order.exchange, order.quantity, price, price
                )
            else:
                total_quantity = state.quantity + order.quantity
                state.entry_price = (
                    state.entry_price * state.quantity + price * order.quantity
                ) / total_quantity
                state.quantity = total_quantity
        else:
            state = self._positions.get(key)
            held = state.quantity if state is not None else 0.0
            if state is None or held < order.quantity:
                raise BrokerValidationError(
                    f"Insufficient position to fill {order_id}: "
                    f"held {held}, requested {order.quantity}"
                )
            realized_pnl = (price - state.entry_price) * order.quantity
            self._cash += price * order.quantity
            self._realized_pnl += realized_pnl
            state.quantity -= order.quantity
            state.realized_pnl += realized_pnl
            if state.quantity <= 0:
                del self._positions[key]

        self._last_prices[key] = price
        fill = PaperFill(
            fill_id=uuid4().hex,
            order_id=order.order_id,
            broker_id=order.broker_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=order.quantity,
            price=price,
            realized_pnl=realized_pnl,
        )
        self._fills.append(fill)
        filled = order.model_copy(update={"status": OrderStatus.FILLED, "updated_at": self._now()})
        self._orders[order_id] = filled
        self._logger.info(
            "Paper order %s filled at %s for %s %s",
            order_id,
            price,
            order.quantity,
            order.symbol,
        )
        return filled, fill

    def update_current_prices(self, prices: Mapping[str, float]) -> None:
        """Refresh position prices from caller-supplied market data.

        Explicit placeholder: the broker does not invent a price source. The
        caller supplies current prices keyed by symbol; positions for those
        symbols are valued at the supplied price when no recorded trade price
        is available.
        """
        for symbol, price in prices.items():
            if price <= 0:
                raise BrokerValidationError(f"current price for {symbol!r} must be positive")
            for key in self._positions:
                if key[0] == symbol:
                    self._positions[key].current_price = price

    def current_price_from_market(self, candles: Sequence[Candle], symbol: str) -> float | None:
        """Return the latest close for ``symbol`` from market candles, if any.

        Used by callers to refresh valuation prices from verified market data
        (AIOS-308 section 12); the broker itself never fabricates prices.
        """
        matches = [candle for candle in candles if candle.symbol == symbol]
        if not matches:
            return None
        return matches[-1].close

    # -- internals ----------------------------------------------------------

    def _get_order(self, order_id: str) -> PaperOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(f"No paper order with id {order_id!r}")
        return order

    def _require_pending(self, order_id: str) -> PaperOrder:
        order = self._get_order(order_id)
        if order.status is not OrderStatus.PENDING:
            raise InvalidOrderStateError(
                f"Order {order_id!r} is {order.status.value}, only PENDING orders "
                "can change state (AIOS-1103 section 11)"
            )
        return order

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
