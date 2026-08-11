"""AIOS standard data models (AIOS-501, AIOS-502, AIOS-503, AIOS-504).

The Data Layer standardizes all incoming information so that every module
consumes identical structures regardless of the original provider
(AIOS-503 section 2, AIOS-505 section 6). Providers translate external
responses into these models (AIOS-603 section 6); analysis engines consume
only these models (AIOS-503 section 1).

These models are domain models — they carry no persistence concerns. Storage
mapping lives in the Database Layer (aios.database.models) behind the
Repository Pattern (AIOS-606).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssetType(str, Enum):
    """Supported asset classes (AIOS-503 section 4).

    Phase 2 documents Equities; additional asset classes are future
    expansion (AIOS-503 section 15).
    """

    EQUITY = "equity"


class MarketStatus(str, Enum):
    """Market status values (AIOS-503 section 10)."""

    OPEN = "open"
    CLOSED = "closed"
    HALTED = "halted"
    SUSPENDED = "suspended"


class SessionStatus(str, Enum):
    """Trading session status values (AIOS-503 section 8)."""

    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"
    CLOSED = "closed"


class Timeframe(str, Enum):
    """Supported candle timeframes (AIOS-503 section 6)."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1mo"


class ComplianceStatus(str, Enum):
    """Shariah compliance status values (AIOS-504 section 6).

    COMPLIANT: security is approved for investment.
    NON_COMPLIANT: security is prohibited.
    UNDER_REVIEW: provider has not completed review.
    UNKNOWN: no reliable compliance information exists.
    """

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    UNDER_REVIEW = "under_review"
    UNKNOWN = "unknown"


class Security(BaseModel):
    """Core market security entity (AIOS-503 section 4).

    Each security is uniquely identified by symbol and exchange and carries
    its trading session and market status.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    exchange: str
    asset_type: AssetType
    currency: str
    trading_session: str
    timezone: str
    market_status: MarketStatus

    @field_validator("symbol", "exchange", "currency", "trading_session", "timezone")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class Candle(BaseModel):
    """Standardized candlestick (AIOS-503 section 5).

    Every candle carries its symbol and timeframe so the model is self
    describing across the supported timeframes (AIOS-503 section 6). Field
    level constraints (open > 0, volume >= 0) follow the validation rules in
    AIOS-503 section 12; cross-field High/Low relationships are enforced by
    the business-rule validator (AIOS-506 Level 3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    open: float = Field(gt=0)
    high: float
    low: float
    close: float
    volume: float = Field(ge=0)
    vwap: float | None = None
    trade_count: int | None = Field(default=None, ge=0)
    average_price: float | None = None

    @field_validator("symbol")
    @classmethod
    def symbol_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be empty")
        return value.strip()


class ShariahCompliance(BaseModel):
    """Shariah compliance record (AIOS-504 sections 4-8).

    Preserves the provider, review/effective/expiration dates, screening
    methodology, and confidence level mandated by AIOS-504. Compliance
    history is never overwritten: every provider review creates a new
    record (AIOS-504 section 9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    company_name: str
    exchange: str
    country: str
    asset_type: AssetType
    compliance_status: ComplianceStatus
    provider: str
    provider_version: str = "1.0.0"
    review_date: date
    effective_date: date
    expiration_date: date | None = None
    screening_methodology: str
    screening_version: str = "1.0.0"
    screening_date: date
    confidence_level: float = Field(default=1.0, ge=0.0, le=1.0)
    previous_status: ComplianceStatus | None = None
    retrieval_timestamp: datetime = Field(default_factory=_utc_now)

    @field_validator("symbol", "company_name", "exchange", "country", "provider")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class CompanyFundamentals(BaseModel):
    """Company financial information (AIOS-502 section 6, AIOS-402 section 6).

    Carries the fundamental metrics consumed by the Fundamental Engine and
    the Decision Engine (AIOS-502 section 6).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    sector: str = ""
    industry: str = ""
    revenue: float | None = None
    net_income: float | None = None
    eps: float | None = None
    assets: float | None = None
    liabilities: float | None = None
    cash_flow: float | None = None
    equity: float | None = None
    report_date: date
    retrieval_timestamp: datetime = Field(default_factory=_utc_now)

    @field_validator("symbol", "sector", "industry")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        return value.strip()


class PositionStatus(str, Enum):
    """Lifecycle status of a portfolio position (AIOS-402 section 8)."""

    OPEN = "open"
    CLOSED = "closed"


class PortfolioPosition(BaseModel):
    """A held security position (AIOS-402 section 8, AIOS-306).

    Tracks holdings: the symbol, quantity, entry price, current price,
    allocation (fraction of portfolio value, 0.0 to 1.0), status, and the
    sector used for sector-distribution reporting (AIOS-206 section 5). The
    current-position view is updated in place as the portfolio changes;
    ``updated_at`` records the last change for allocation-change tracking
    (AIOS-206 section 8).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    exchange: str
    quantity: float = Field(ge=0)
    entry_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    allocation: float = Field(ge=0.0, le=1.0)
    sector: str = ""
    status: PositionStatus = PositionStatus.OPEN
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("symbol", "exchange")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class DecisionAction(str, Enum):
    """Supported investment decision types (AIOS-208 section 5, AIOS-208 section 10).

    BUY, HOLD, SELL, and WAIT are the documented directions (AIOS-208
    section 5); NO TRADE is a valid no-action decision the system must allow
    to avoid forced trading (AIOS-208 section 10).
    """

    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    WAIT = "wait"
    NO_TRADE = "no_trade"


class InvestmentDecision(BaseModel):
    """A stored investment decision (AIOS-402 section 9, AIOS-208 section 7).

    Records the symbol, decision direction, reason, confidence score, risk
    score, and timestamp mandated by AIOS-402. The explanation content from
    AIOS-208 section 7 (supporting data, risk level, decision score) is
    carried in ``supporting_data`` so decision history remains explainable
    and complete (AIOS-208 section 11).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    decision: DecisionAction
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=_utc_now)
    supporting_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def symbol_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be empty")
        return value.strip()


# =============================================================================
# Corporate Actions Models (Phase 9.3+)
# =============================================================================


class CorporateActionType(str, Enum):
    """Types of corporate actions affecting securities."""

    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    DIVIDEND = "dividend"
    SPINOFF = "spinoff"
    MERGER = "merger"
    ACQUISITION = "acquisition"
    TICKER_CHANGE = "ticker_change"
    DELISTING = "delisting"
    BANKRUPTCY = "bankruptcy"


class CorporateAction(BaseModel):
    """Corporate action affecting a security (Phase 9.3+).

    Represents corporate events that affect price, quantity, or identity
    of a security. Used for historical price/fundamental adjustment in backtesting.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    action_type: CorporateActionType
    effective_date: date
    ratio: float | None = Field(default=None, description="For splits: new/old ratio. For dividends: amount per share")
    old_ticker: str | None = None
    new_ticker: str | None = None
    cash_amount: float | None = Field(default=None, description="Cash dividend amount per share")
    description: str = ""
    announced_at: datetime | None = None
    recorded_at: datetime = Field(default_factory=_utc_now)

    @field_validator("symbol")
    @classmethod
    def symbol_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be empty")
        return value.strip()


class CorporateActionProvider(Protocol):
    """Interface for retrieving corporate actions (Phase 9.3+).

    Implementations provide corporate action data for backtesting
    to adjust prices, quantities, and fundamentals for corporate events.
    """

    def get_actions(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateAction]:
        """Get corporate actions for a symbol within a date range."""
        ...

    def get_actions_for_symbols(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, list[CorporateAction]]:
        """Get corporate actions for multiple symbols."""
        ...


# =============================================================================
# Survivorship Bias Handling (Phase 9.3+)
# =============================================================================


class SecurityLifecycleStatus(str, Enum):
    """Lifecycle status of a security for survivorship bias handling."""

    ACTIVE = "active"
    DELISTED = "delisted"
    ACQUIRED = "acquired"
    BANKRUPT = "bankrupt"
    MERGED = "merged"
    TICKER_CHANGED = "ticker_changed"


class SecurityLifecycle(BaseModel):
    """Security lifecycle tracking for survivorship bias handling (Phase 9.3+).

    Tracks the lifecycle events of a security to enable proper
    survivorship bias handling in backtesting.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    exchange: str
    status: SecurityLifecycleStatus
    listed_date: date | None = None
    delisted_date: date | None = None
    delisting_reason: str | None = None
    successor_symbol: str | None = None
    successor_exchange: str | None = None
    corporate_actions: list[CorporateAction] = Field(default_factory=list)

    @field_validator("symbol", "exchange")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class HistoricalUniverseProvider(Protocol):
    """Interface for retrieving historical universe including delisted securities (Phase 9.3+).

    Enables survivorship-bias-free backtesting by providing access to
    the complete historical universe including delisted/acquired securities.
    """

    def get_universe_as_of(self, as_of: date) -> list[str]:
        """Get all symbols that were tradeable as of the given date."""
        ...

    def get_symbol_lifecycle(self, symbol: str) -> SecurityLifecycle | None:
        """Get the lifecycle record for a symbol."""
        ...

    def get_corporate_action_provider(self) -> CorporateActionProvider:
        """Get the corporate action provider for this universe."""
        ...


# =============================================================================
# Historical Data Provider (Extended for Backtesting)
# =============================================================================


class PointInTimeDataProvider(Protocol):
    """Extended data provider interface for point-in-time backtesting (Phase 9.5).

    Extends the standard data provider with point-in-time query capabilities
    and corporate action awareness.
    """

    def get_candles_point_in_time(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        as_of: datetime,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[Candle]:
        """Get candles as of a specific point in time (no look-ahead)."""
        ...

    def get_fundamentals_point_in_time(
        self,
        symbol: str,
        *,
        as_of: date,
        report_date: date | None = None,
    ) -> CompanyFundamentals | None:
        """Get fundamentals as of a specific date (point-in-time)."""
        ...

    def get_corporate_actions(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateAction]:
        """Get corporate actions affecting a symbol within a date range."""
        ...

    def get_symbol_lifecycle(self, symbol: str) -> SecurityLifecycle | None:
        """Get the lifecycle record for a symbol."""
        ...

    def get_historical_universe(self, as_of: date) -> list[str]:
        """Get all symbols that were tradeable as of a given date."""
        ...
