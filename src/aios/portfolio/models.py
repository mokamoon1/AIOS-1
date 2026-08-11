"""Portfolio domain models (AIOS-206 sections 5-8, AIOS-306 section 8).

The snapshot reflects the current-holdings view owned by the Portfolio
Module (AIOS-501 section 7, AIOS-603 section 10). All values are objective
arithmetic on stored position data: no allocation target, threshold, or
opinion is invented here (AIOS-206 section 12).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PositionHolding(BaseModel):
    """A single open position with computed objective metrics (AIOS-306 section 8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    exchange: str
    quantity: float
    entry_price: float
    current_price: float
    sector: str
    market_value: float = Field(ge=0.0)
    allocation: float = Field(ge=0.0, le=1.0)
    unrealized_pnl: float
    return_pct: float


class SectorAllocation(BaseModel):
    """Objective sector concentration for the portfolio (AIOS-206 section 7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sector: str
    market_value: float = Field(ge=0.0)
    count: int = Field(ge=0)
    allocation: float = Field(ge=0.0, le=1.0)

    @field_validator("sector")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sector must not be empty")
        return value.strip()


class PortfolioSnapshot(BaseModel):
    """A read-only snapshot of the current portfolio (AIOS-603 section 10).

    Reports concentration and performance as objective values only; the
    documented outputs of the Portfolio Agent (recommended allocation and
    rebalance suggestion) require target allocation rules that are not yet
    defined and are therefore not fabricated here (AIOS-403 section 10).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: datetime
    total_value: float = Field(ge=0.0)
    position_count: int = Field(ge=0)
    sector_count: int = Field(ge=0)
    positions: list[PositionHolding] = Field(default_factory=list)
    sectors: list[SectorAllocation] = Field(default_factory=list)
    max_position_allocation: float = Field(ge=0.0, le=1.0)
    max_sector_allocation: float = Field(ge=0.0, le=1.0)
    weighted_return_pct: float


# =============================================================================
# Portfolio Target Allocation Models (Phase 9.4)
# =============================================================================

class AllocationAction(str, Enum):
    """Action for a recommended allocation change."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TargetAllocation(BaseModel):
    """Target allocation for a single symbol (Phase 9.4).

    Represents the recommended target weight and action for a position.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    exchange: str = "NASDAQ"
    target_weight: float = Field(ge=0.0, le=1.0)
    target_value: float = Field(ge=0.0)
    current_weight: float = Field(ge=0.0, le=1.0)
    current_value: float = Field(ge=0.0)
    action: AllocationAction
    allocation_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    risk_adjustment: float = Field(ge=0.0, le=1.0)
    hard_constraints_triggered: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @field_validator("symbol", "exchange")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class RebalanceSuggestion(BaseModel):
    """Rebalancing suggestion for the portfolio (Phase 9.4).

    Recommends trades to move current portfolio toward target allocations.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    required: bool
    reason: str
    trades: list[TargetAllocation] = Field(default_factory=list)
    portfolio_drift: float = Field(ge=0.0, le=1.0)
    estimated_turnover: float = Field(ge=0.0)


class PortfolioAllocationResult(BaseModel):
    """Complete portfolio allocation result (Phase 9.4).

    Contains recommended allocations for all symbols and rebalancing suggestions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: datetime
    total_portfolio_value: float = Field(ge=0.0)
    target_allocations: list[TargetAllocation] = Field(default_factory=list)
    rebalance_suggestion: Optional[RebalanceSuggestion] = None
    hard_constraints_triggered: list[str] = Field(default_factory=list)
    explanation: str = ""

    @field_validator("explanation")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explanation must not be empty")
        return value.strip()
