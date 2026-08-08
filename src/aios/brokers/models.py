"""Broker domain models (AIOS-407 section 4.3, AIOS-1103 section 11).

Paper Trading is the only execution mode in the current phase (AIOS-101
section 4.6, AIOS-208 section 8, AIOS-603 section 11). Order status values
follow the documented enum (AIOS-1103 section 11): PENDING, FILLED,
CANCELLED, REJECTED. The broker abstraction deliberately carries no slippage,
fee, latency, or position-sizing rules because none are documented
(AIOS-208 section 9, AIOS-406 section 7).

These models are domain models — they carry no persistence concerns. Storage
mapping lives in the Database Layer (aios.database.models) behind the
Repository Pattern (AIOS-606).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrderSide(str, Enum):
    """Direction of a trading order (AIOS-1101, AIOS-208 section 5).

    Only BUY and SELL are actionable; HOLD, WAIT, and NO TRADE decisions never
    create orders (AIOS-208 section 10).
    """

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Paper order lifecycle statuses (AIOS-1103 section 11)."""

    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PaperOrder(BaseModel):
    """A paper order submitted to a broker (AIOS-1101, AIOS-407 section 4.3).

    Records the symbol, exchange, side, quantity, price, lifecycle status,
    and the decision that approved it (``decision_ref``) so execution remains
    traceable to the approved recommendation (AIOS-208 section 11, ADR-0002).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    broker_id: str
    symbol: str
    exchange: str
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    status: OrderStatus = OrderStatus.PENDING
    reason: str = ""
    decision_ref: str | None = None
    submitted_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("order_id", "broker_id", "symbol", "exchange")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class PaperFill(BaseModel):
    """A recorded fill for a paper order (AIOS-101 section 4.6).

    Fills are explicit records: they are never fabricated by an automatic
    fill, slippage, or latency model (AIOS-208 section 9). ``realized_pnl``
    is the objective arithmetic realized profit/loss of a sell fill computed
    from the recorded average entry price at the time of the fill.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: str
    order_id: str
    broker_id: str
    symbol: str
    exchange: str
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    realized_pnl: float = 0.0
    filled_at: datetime = Field(default_factory=_utc_now)

    @field_validator("fill_id", "order_id", "broker_id", "symbol", "exchange")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class BrokerAccount(BaseModel):
    """Broker account status (AIOS-407 section 4.3 "Check Account").

    Carries the current cash and the initial paper capital. The initial
    capital is a configurable placeholder because the approved documents do
    not fix the starting paper balance (AIOS-407 section 4.3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    account_id: str
    currency: str
    cash: float = Field(ge=0)
    initial_cash: float = Field(gt=0)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("broker_id", "account_id", "currency")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class BrokerPosition(BaseModel):
    """An open position held at the broker (AIOS-407 section 4.3).

    Objective arithmetic on recorded fills: entry price is the average entry
    cost, market value is ``current_price * quantity``, unrealized P&L is
    ``(current_price - entry_price) * quantity`` (AIOS-306 section 8).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    exchange: str
    quantity: float = Field(ge=0)
    entry_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    market_value: float = Field(ge=0)
    unrealized_pnl: float
    realized_pnl: float = 0.0
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("symbol", "exchange")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class PortfolioStatus(BaseModel):
    """Broker portfolio status (AIOS-407 section 4.3 "Get Portfolio Status").

    ``equity`` is the objective sum of cash and the market value of open
    positions; ``realized_pnl`` is the sum of recorded sell-fill P&L.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    account_id: str
    currency: str
    cash: float = Field(ge=0)
    market_value: float = Field(ge=0)
    equity: float = Field(ge=0)
    realized_pnl: float = 0.0
    position_count: int = Field(ge=0)
    positions: list[BrokerPosition] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("broker_id", "account_id", "currency")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class PerformanceSnapshot(BaseModel):
    """Objective paper-trading performance snapshot (AIOS-308 section 12).

    Every value is arithmetic on recorded data (orders, fills, positions,
    account). No benchmark, target return, Sharpe threshold, drawdown
    threshold, fee, or slippage model is invented here because none of those
    are documented (AIOS-208 section 9, AIOS-406 section 7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: datetime = Field(default_factory=_utc_now)
    broker_id: str
    account_id: str
    currency: str
    initial_cash: float = Field(gt=0)
    cash: float = Field(ge=0)
    market_value: float = Field(ge=0)
    equity: float = Field(ge=0)
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_return_pct: float
    order_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    position_count: int = Field(ge=0)
    positions: list[BrokerPosition] = Field(default_factory=list)

    @field_validator("broker_id", "account_id", "currency")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()
