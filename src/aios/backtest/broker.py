"""Backtest Paper Broker - Execution simulation with transaction costs (Phase 9.5).

Extends the Paper Broker with configurable transaction costs, slippage models,
and fill policies for realistic backtest execution simulation.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import final
from uuid import uuid4

from aios.backtest.models import FillPolicy, SlippageModel, TransactionCostConfig
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
from aios.brokers.paper import PaperBroker, _PositionState
from aios.data.models import Candle


@final
class BacktestPaperBroker:
    """Backtest Paper Trading broker with configurable transaction costs.

    Extends the PaperBroker with:
    - Commission (basis points)
    - Bid-ask spread
    - Configurable slippage models (fixed, volume-weighted, square-root)
    - Fill policies (exact, next_open, vwap)
    - Current backtest timestamp for deterministic fills

    All execution parameters are configured via TransactionCostConfig.
    """

    def __init__(
        self,
        broker_id: str,
        account_id: str,
        initial_cash: float = 100_000.0,
        currency: str = "USD",
        transaction_costs: TransactionCostConfig | None = None,
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
        self._positions: dict[tuple[str, str], _PositionState] = {}
        self._last_prices: dict[tuple[str, str], float] = {}
        self._realized_pnl = 0.0
        self._logger = logger or logging.getLogger("aios.backtest.broker")

        # Transaction costs
        self._costs = transaction_costs or TransactionCostConfig()

        # Current backtest timestamp (set by orchestrator)
        self._current_time: datetime | None = None

        # Pending orders for NEXT_OPEN fill policy
        self._pending_orders: list[PaperOrder] = []

        # Reference to backtest data service for price lookups
        self._backtest_data_service: "BacktestDataService | None" = None

    # -- identity ----------------------------------------------------------

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def current_time(self) -> datetime | None:
        return self._current_time

    def set_current_time(self, current_time: datetime) -> None:
        """Set the current backtest timestamp (called by orchestrator).
        
        For NEXT_OPEN fill policy, this fills pending orders at the new timestamp's open price.
        """
        if current_time.tzinfo is None:
            raise ValueError("current_time must be timezone-aware (UTC)")
        
        # Fill pending orders at the new timestamp's open price (NEXT_OPEN policy)
        if self._costs.fill_policy == FillPolicy.NEXT_OPEN and self._current_time is not None:
            self._fill_pending_orders_at_open()
        
        self._current_time = current_time

    def set_backtest_data_service(self, service: "BacktestDataService") -> None:
        """Set the backtest data service for price lookups (called by orchestrator)."""
        self._backtest_data_service = service

    def _fill_pending_orders_at_open(self) -> None:
        """Fill all pending orders at the current timestamp's open price (NEXT_OPEN policy) or VWAP (VWAP policy)."""
        if not self._pending_orders:
            return
        
        fill_policy = self._costs.fill_policy
        
        if fill_policy == FillPolicy.NEXT_OPEN:
            self._fill_pending_orders_next_open()
        elif fill_policy == FillPolicy.VWAP:
            self._fill_pending_orders_vwap()
        # EXACT policy doesn't queue orders - they're filled immediately via fill_order()

    # -- identity ----------------------------------------------------------

    # -- documented operations (AIOS-407 section 4.3) ----------------------

    def check_account(self) -> BrokerAccount:
        return BrokerAccount(
            broker_id=self._broker_id,
            account_id=self._account_id,
            currency=self._currency,
            cash=self._cash,
            initial_cash=self._initial_cash,
        )

    def submit_order(self, order: PaperOrder) -> PaperOrder:
        """Submit a paper order and return it in the PENDING state.
        
        For NEXT_OPEN fill policy, orders are queued and filled at the next timestamp's open price.
        For EXACT fill policy, orders are immediately pending (legacy behavior).
        """
        if order.order_id in self._orders:
            raise OrderAlreadyExistsError(f"Order {order.order_id!r} was already submitted")
        if order.broker_id != self._broker_id:
            raise BrokerValidationError(
                f"Order {order.order_id!r} belongs to broker {order.broker_id!r}, "
                f"not {self._broker_id!r}"
            )
        
        if self._costs.fill_policy == FillPolicy.NEXT_OPEN:
            # Queue order for next timestamp's open
            order = order.model_copy(update={"status": OrderStatus.PENDING})
            self._pending_orders.append(order)
            self._logger.info(
                "Backtest order %s queued for NEXT_OPEN: %s %s %s x %s",
                order.order_id,
                order.side.value,
                order.symbol,
                order.quantity,
                order.price,
            )
        else:
            # EXACT fill policy - immediate PENDING (legacy behavior)
            self._orders[order.order_id] = order
            self._logger.info(
                "Backtest order %s submitted: %s %s %s x %s",
                order.order_id,
                order.side.value,
                order.symbol,
                order.quantity,
                order.price,
            )
        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        order = self._require_pending(order_id)
        updated = order.model_copy(
            update={
                "status": OrderStatus.CANCELLED,
                "reason": "cancelled",
                "updated_at": self._now(),
            }
        )
        self._orders[order_id] = updated
        self._logger.info("Backtest order %s cancelled", order_id)
        return updated

    def reject_order(self, order_id: str, *, reason: str) -> PaperOrder:
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
        self._logger.info("Backtest order %s rejected: %s", order_id, reason)
        return updated

    def get_order(self, order_id: str) -> PaperOrder:
        return self._get_order(order_id)

    def list_orders(self) -> list[PaperOrder]:
        return list(self._orders.values())

    def get_positions(self) -> list[BrokerPosition]:
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

    def fill_order(self, order_id: str, *, price: float, quantity: float | None = None) -> tuple[PaperOrder, PaperFill]:
        """Fill a PENDING order at the given price with transaction costs applied.

        The fill price is adjusted for slippage and spread according to
        the configured transaction cost model. Commission is deducted from cash.

        Supports partial fills via min_fill_fraction and min_trade_size settings.
        """
        order = self._require_pending(order_id)
        if not price or price <= 0:
            raise BrokerValidationError("fill price must be positive")

        # Determine fill quantity (support partial fills)
        requested_qty = order.quantity
        fill_qty = quantity if quantity is not None else requested_qty

        # Enforce minimum trade size
        min_trade = self._costs.min_trade_size
        if min_trade > 0 and fill_qty < min_trade:
            raise BrokerValidationError(
                f"Fill quantity {fill_qty} below minimum trade size {min_trade}"
            )

        # Enforce minimum fill fraction
        min_frac = self._costs.min_fill_fraction
        if min_frac > 0:
            min_qty = requested_qty * min_frac
            if fill_qty < min_qty:
                raise BrokerValidationError(
                    f"Fill quantity {fill_qty} below minimum fill fraction {min_frac} "
                    f"(minimum {min_qty:.4f})"
                )

        # Apply slippage and spread to get actual fill price
        fill_price = self._apply_transaction_costs(order.side, price, order=order)
        commission = self._calculate_commission(fill_price, fill_qty)

        key = (order.symbol, order.exchange)
        realized_pnl = 0.0

        if order.side is OrderSide.BUY:
            cost = fill_price * fill_qty
            total_cost = cost + commission
            if total_cost > self._cash:
                raise BrokerValidationError(
                    f"Insufficient cash to fill {order_id}: "
                    f"need {total_cost:.2f} (cost {cost:.2f} + commission {commission:.2f}), "
                    f"have {self._cash:.2f}"
                )
            self._cash -= total_cost
            state = self._positions.get(key)
            if state is None:
                self._positions[key] = _PositionState(
                    order.symbol, order.exchange, fill_qty, fill_price, fill_price
                )
            else:
                total_quantity = state.quantity + fill_qty
                state.entry_price = (
                    state.entry_price * state.quantity + fill_price * fill_qty
                ) / total_quantity
                state.quantity = total_quantity
        else:
            state = self._positions.get(key)
            held = state.quantity if state is not None else 0.0
            if state is None or held < fill_qty:
                raise BrokerValidationError(
                    f"Insufficient position to fill {order_id}: "
                    f"held {held}, requested {fill_qty}"
                )
            realized_pnl = (fill_price - state.entry_price) * fill_qty
            self._cash += fill_price * fill_qty - commission
            self._realized_pnl += realized_pnl
            state.quantity -= fill_qty
            state.realized_pnl += realized_pnl
            if state.quantity <= 0:
                del self._positions[key]

        self._last_prices[key] = fill_price
        fill = PaperFill(
            fill_id=uuid4().hex,
            order_id=order.order_id,
            broker_id=order.broker_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=fill_qty,
            price=fill_price,
            realized_pnl=realized_pnl,
        )
        self._fills.append(fill)

        # Update order status
        remaining_qty = requested_qty - fill_qty
        if remaining_qty <= 0:
            # Full fill
            filled = order.model_copy(update={"status": OrderStatus.FILLED, "updated_at": self._now()})
            self._orders[order_id] = filled
            self._logger.info(
                "Backtest order %s filled at %s (raw=%s) for %s %s, commission=%.2f",
                order_id,
                fill_price,
                price,
                fill_qty,
                order.symbol,
                commission,
            )
        else:
            # Partial fill - update order with remaining quantity
            updated_order = order.model_copy(update={"quantity": remaining_qty, "updated_at": self._now()})
            self._orders[order_id] = updated_order
            self._logger.info(
                "Backtest order %s partially filled at %s (raw=%s) for %s/%s %s, commission=%.2f",
                order_id,
                fill_price,
                price,
                fill_qty,
                requested_qty,
                order.symbol,
                commission,
            )

        fill = PaperFill(
            fill_id=uuid4().hex,
            order_id=order.order_id,
            broker_id=order.broker_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=fill_qty,
            price=fill_price,
            realized_pnl=realized_pnl,
        )
        self._fills.append(fill)

        if remaining_qty <= 0:
            filled = order.model_copy(update={"status": OrderStatus.FILLED, "updated_at": self._now()})
            self._orders[order_id] = filled
            self._logger.info(
                "Backtest order %s filled at %s (raw=%s) for %s %s, commission=%.2f",
                order_id,
                fill_price,
                price,
                fill_qty,
                order.symbol,
                commission,
            )
        else:
            # Partial fill - update order with remaining quantity
            updated_order = order.model_copy(update={"quantity": remaining_qty, "updated_at": self._now()})
            self._orders[order_id] = updated_order
            self._logger.info(
                "Backtest order %s partially filled at %s (raw=%s) for %s/%s %s, commission=%.2f",
                order_id,
                fill_price,
                price,
                fill_qty,
                requested_qty,
                order.symbol,
                commission,
            )

        return filled, fill

    def update_current_prices(self, prices: Mapping[str, float]) -> None:
        """Refresh position prices from caller-supplied market data."""
        for symbol, price in prices.items():
            if price <= 0:
                raise BrokerValidationError(f"current price for {symbol!r} must be positive")
            for key in self._positions:
                if key[0] == symbol:
                    self._positions[key].current_price = price

    def current_price_from_market(self, candles: Sequence[Candle], symbol: str) -> float | None:
        matches = [candle for candle in candles if candle.symbol == symbol]
        if not matches:
            return None
        return matches[-1].close

    def set_current_time(self, current_time: datetime) -> None:
        """Set the current backtest timestamp (called by orchestrator)."""
        if current_time.tzinfo is None:
            raise ValueError("current_time must be timezone-aware (UTC)")
        self._current_time = current_time

    # -- state restoration ----------------------------------------------------

    def restore_account(self, account: BrokerAccount) -> None:
        if account.broker_id != self._broker_id:
            raise BrokerValidationError(
                f"Account broker_id {account.broker_id!r} does not match "
                f"broker {self._broker_id!r}"
            )
        if account.account_id != self._account_id:
            raise BrokerValidationError(
                f"Account account_id {account.account_id!r} does not match "
                f"broker account {self._account_id!r}"
            )
        self._cash = account.cash
        self._initial_cash = account.initial_cash
        self._logger.info(
            "Restored backtest broker account: cash=%.2f, initial_cash=%.2f",
            self._cash,
            self._initial_cash,
        )

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
        return self._current_time or datetime.now(timezone.utc)

    # -- transaction cost calculations ---------------------------------------

    def _apply_transaction_costs(self, side: OrderSide, raw_price: float) -> float:
        """Apply slippage and spread to get actual fill price."""
        spread_adj = self._costs.spread_bps / 10000.0
        slippage_adj = self._calculate_slippage(side)

        if side == OrderSide.BUY:
            # Buy at higher price (ask + spread/2 + slippage)
            return raw_price * (1.0 + spread_adj / 2.0 + slippage_adj)
        else:
            # Sell at lower price (bid - spread/2 - slippage)
            return raw_price * (1.0 - spread_adj / 2.0 - slippage_adj)

    def _calculate_slippage(self, side: OrderSide, order: PaperOrder | None = None) -> float:
        """Calculate slippage adjustment based on configured model.
        
        For VOLUME_WEIGHTED: slippage scales with order size relative to average daily volume
        For SQUARE_ROOT: uses square-root market impact model (Almgren-Chriss style)
        For FIXED: constant slippage regardless of order size
        """
        base_bps = self._costs.slippage_bps / 10000.0
        
        if self._costs.slippage_model == SlippageModel.FIXED:
            return base_bps
            
        # For volume-dependent models, we need order quantity and market data
        if order is None:
            self._logger.warning("Order not provided for volume-dependent slippage, using fixed")
            return base_bps
            
        if self._costs.slippage_model == SlippageModel.VOLUME_WEIGHTED:
            # Volume-weighted: slippage scales with order size relative to average daily volume
            # slippage = base_bps * sqrt(order_qty / avg_daily_volume)
            # For backtest, we estimate ADV from historical data
            adv = self._estimate_average_daily_volume(order.symbol)
            if adv > 0:
                volume_ratio = order.quantity / adv
                return base_bps * math.sqrt(max(volume_ratio, 0.0))
            return base_bps
            
        elif self._costs.slippage_model == SlippageModel.SQUARE_ROOT:
            # Square-root market impact model (Almgren-Chriss style)
            # impact = k * sigma * sqrt(Q / ADV) where k ~ 0.5-1.0, sigma is daily volatility
            adv = self._estimate_average_daily_volume(order.symbol)
            if adv > 0:
                volatility = self._estimate_daily_volatility(order.symbol)
                quantity = order.quantity
                # Square-root model: k * sigma * sqrt(Q/ADV)
                # k ~ 1.0 for typical market impact
                impact = 1.0 * volatility * math.sqrt(max(order.quantity / adv, 0.0))
                # Convert to bps
                return impact * 10000.0
            return base_bps
            
        return base_bps
    
    def _estimate_average_daily_volume(self, symbol: str) -> float:
        """Estimate average daily volume from historical data."""
        if self._backtest_data_service is None:
            return 1_000_000.0  # Default fallback
        try:
            candles = self._backtest_data_service.get_candles(
                symbol=symbol,
                timeframe=Timeframe.ONE_DAY,
                limit=30,  # Last 30 days for ADV
            )
            if not candles:
                return 1_000_000.0
            avg_volume = sum(c.volume for c in candles) / len(candles)
            return max(avg_volume, 1.0)
        except Exception:
            return 1_000_000.0
    
    def _estimate_daily_volatility(self, symbol: str) -> float:
        """Estimate daily volatility from historical returns."""
        if self._backtest_data_service is None:
            return 0.02  # 2% default
        try:
            candles = self._backtest_data_service.get_candles(
                symbol=symbol,
                timeframe=Timeframe.ONE_DAY,
                limit=30,
            )
            if len(candles) < 2:
                return 0.02
            returns = []
            for i in range(1, len(candles)):
                prev_close = candles[i-1].close
                curr_close = candles[i].close
                if prev_close > 0:
                    returns.append((curr_close - prev_close) / prev_close)
            if not returns:
                return 0.02
            return float(np.std(returns))
        except Exception:
            return 0.02

    def _calculate_commission(self, price: float, quantity: float) -> float:
        """Calculate commission in base currency."""
        notional = price * quantity
        return notional * (self._costs.commission_bps / 10000.0)

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
        return self._current_time or datetime.now(timezone.utc)