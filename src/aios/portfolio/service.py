"""Portfolio service (AIOS-206, AIOS-603 section 10).

The service computes an objective :class:`PortfolioSnapshot` from stored
positions and provides the current-holdings view the Portfolio Agent
consumes (AIOS-501 section 7). Positions are read through the injected
reader facade so this module never touches the database directly
(AIOS-605 section 13, AIOS-606 section 1); when no reader is configured the
service degrades with a documented error instead of guessing values
(AIOS-206 section 12).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol

from aios.data.models import PortfolioPosition, PositionStatus
from aios.errors import DatabaseError, DataError
from aios.portfolio.exceptions import PortfolioError
from aios.portfolio.models import PortfolioSnapshot, PositionHolding, SectorAllocation


def _utc_now() -> datetime:
    """Return the current UTC timestamp (naive, mirroring the data layer)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PortfolioPositionsReader(Protocol):
    """Read interface satisfied by the Data Layer facade (AIOS-501 section 2)."""

    def list_positions(
        self, *, status: PositionStatus | None = None
    ) -> Sequence[PortfolioPosition]: ...


class PortfolioService:
    """Computes objective portfolio metrics from stored positions (AIOS-603 section 10).

    All metrics (market value, allocation, unrealized P&L, return, sector
    concentration) are arithmetic on stored position data. No target
    allocation, threshold, or rebalancing rule is introduced here because
    such rules are not documented (AIOS-206 sections 6 and 9).
    """

    def __init__(self, reader: PortfolioPositionsReader | None = None) -> None:
        self._reader = reader

    @property
    def reader(self) -> PortfolioPositionsReader | None:
        """The positions reader this service reads from (None until wired)."""
        return self._reader

    def build_snapshot(self, positions: Sequence[PortfolioPosition]) -> PortfolioSnapshot:
        """Build an objective portfolio snapshot from open positions.

        Only positions with :attr:`PositionStatus.OPEN` are included; closed
        positions are history, not holdings (AIOS-306 section 8).
        """
        holdings: list[PositionHolding] = []
        sector_value: dict[str, float] = {}
        sector_count: dict[str, int] = {}
        total_value = 0.0
        weighted_return = 0.0
        for position in positions:
            if position.status is not PositionStatus.OPEN:
                continue
            market_value = position.current_price * position.quantity
            unrealized_pnl = (position.current_price - position.entry_price) * position.quantity
            return_pct = (
                (position.current_price - position.entry_price) / position.entry_price * 100.0
            )
            holdings.append(
                PositionHolding(
                    symbol=position.symbol,
                    exchange=position.exchange,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    sector=position.sector,
                    market_value=market_value,
                    allocation=position.allocation,
                    unrealized_pnl=unrealized_pnl,
                    return_pct=return_pct,
                )
            )
            total_value += market_value
            weighted_return += position.allocation * return_pct
            sector = position.sector.strip()
            if sector:
                sector_value[sector] = sector_value.get(sector, 0.0) + market_value
                sector_count[sector] = sector_count.get(sector, 0) + 1

        sectors = [
            SectorAllocation(
                sector=sector,
                market_value=value,
                count=sector_count[sector],
                allocation=(value / total_value) if total_value > 0 else 0.0,
            )
            for sector, value in sector_value.items()
        ]
        sectors.sort(key=lambda entry: entry.market_value, reverse=True)

        return PortfolioSnapshot(
            generated_at=_utc_now(),
            total_value=total_value,
            position_count=len(holdings),
            sector_count=len(sectors),
            positions=holdings,
            sectors=sectors,
            max_position_allocation=(
                max(holding.allocation for holding in holdings) if holdings else 0.0
            ),
            max_sector_allocation=max((entry.allocation for entry in sectors), default=0.0),
            weighted_return_pct=weighted_return,
        )

    def current_snapshot(self) -> PortfolioSnapshot:
        """Build the current snapshot from the configured reader.

        Raises :class:`PortfolioError` when no reader is configured or the
        data layer cannot supply positions; the caller degrades gracefully
        instead of fabricating portfolio values (AIOS-206 section 12).
        """
        if self._reader is None:
            raise PortfolioError(
                "PortfolioService requires a positions reader to build a current snapshot"
            )
        try:
            positions = list(self._reader.list_positions())
        except (DataError, DatabaseError) as exc:
            raise PortfolioError(f"Could not read current positions: {exc}") from exc
        return self.build_snapshot(positions)
