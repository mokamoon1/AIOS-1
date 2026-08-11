"""AIOS Portfolio module (AIOS-206, AIOS-306, AIOS-603 section 10).

Responsible for portfolio state, asset allocation, position tracking,
performance evaluation, and rebalancing support. The module does not
execute trades directly (AIOS-603 section 10).
"""

from __future__ import annotations

from aios.portfolio.exceptions import PortfolioError
from aios.portfolio.models import (
    AllocationAction,
    PortfolioAllocationResult,
    PortfolioSnapshot,
    PositionHolding,
    RebalanceSuggestion,
    SectorAllocation,
    TargetAllocation,
)
from aios.portfolio.service import PortfolioPositionsReader, PortfolioService

__all__ = [
    "AllocationAction",
    "PortfolioAllocationResult",
    "PortfolioError",
    "PortfolioPositionsReader",
    "PortfolioService",
    "PortfolioSnapshot",
    "PositionHolding",
    "RebalanceSuggestion",
    "SectorAllocation",
    "TargetAllocation",
]
