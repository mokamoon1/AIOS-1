"""Portfolio domain models (AIOS-206 sections 5-8, AIOS-306 section 8).

The snapshot reflects the current-holdings view owned by the Portfolio
Module (AIOS-501 section 7, AIOS-603 section 10). All values are objective
arithmetic on stored position data: no allocation target, threshold, or
opinion is invented here (AIOS-206 section 12).
"""

from __future__ import annotations

from datetime import datetime

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
