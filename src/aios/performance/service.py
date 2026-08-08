"""Performance Tracking service (AIOS-308 section 12, AIOS-603 section 10).

The service computes an objective :class:`PerformanceSnapshot` from recorded
paper-trading data: orders, fills, positions, and the broker account
(AIOS-101 section 4.6). Every metric is arithmetic on recorded values — no
benchmark, target return, Sharpe threshold, drawdown threshold, fee, or
slippage model is invented here because none of those are documented
(AIOS-208 section 9, AIOS-406 section 7).

Data is read through the injected reader facade so this module never touches
the database directly (AIOS-605 section 13, AIOS-606 section 1); when no
reader is configured the service degrades with a documented error instead of
guessing values (mirroring the Portfolio Service, AIOS-206 section 12).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol

from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderStatus,
    PaperFill,
    PaperOrder,
    PerformanceSnapshot,
)
from aios.errors import DatabaseError, DataError
from aios.performance.exceptions import PerformanceError


def _utc_now() -> datetime:
    """Return the current UTC timestamp (naive, mirroring the data layer)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PerformanceDataReader(Protocol):
    """Read interface satisfied by the Data Layer facade (AIOS-501 section 2)."""

    def get_broker_account(self, broker_id: str) -> BrokerAccount: ...

    def list_paper_orders(self, *, status: OrderStatus | None = None) -> list[PaperOrder]: ...

    def list_paper_fills(self, *, order_id: str | None = None) -> list[PaperFill]: ...

    def list_paper_positions(self) -> list[BrokerPosition]: ...


class PerformanceService:
    """Computes objective paper-trading performance from recorded data (AIOS-308).

    All metrics are arithmetic on recorded data. The snapshot is built either
    from caller-supplied data (``build_snapshot``) or from the configured
    reader (``current_snapshot``), matching the Portfolio Service style.
    """

    def __init__(self, reader: PerformanceDataReader | None = None) -> None:
        self._reader = reader

    @property
    def reader(self) -> PerformanceDataReader | None:
        """The data reader this service reads from (None until wired)."""
        return self._reader

    def build_snapshot(
        self,
        *,
        account: BrokerAccount,
        orders: Sequence[PaperOrder],
        fills: Sequence[PaperFill],
        positions: Sequence[BrokerPosition],
    ) -> PerformanceSnapshot:
        """Build an objective performance snapshot from recorded data.

        Metrics:
            * ``order_count`` / ``fill_count`` — recorded order and fill totals.
            * ``realized_pnl`` — sum of recorded fill P&L (AIOS-101 section 4.6).
            * ``unrealized_pnl`` — ``(current_price - entry_price) * quantity``
              per open position (AIOS-306 section 8).
            * ``market_value`` — ``current_price * quantity`` per position.
            * ``equity`` — cash plus market value.
            * ``total_pnl`` — realized plus unrealized.
            * ``total_return_pct`` — ``total_pnl / initial_cash * 100``.
        """
        realized_pnl = sum(fill.realized_pnl for fill in fills)
        unrealized_pnl = sum(position.unrealized_pnl for position in positions)
        market_value = sum(position.market_value for position in positions)
        total_pnl = realized_pnl + unrealized_pnl
        equity = account.cash + market_value
        total_return_pct = (total_pnl / account.initial_cash) * 100.0

        ordered_positions = sorted(
            positions, key=lambda position: (position.symbol, position.exchange)
        )
        return PerformanceSnapshot(
            generated_at=_utc_now(),
            broker_id=account.broker_id,
            account_id=account.account_id,
            currency=account.currency,
            initial_cash=account.initial_cash,
            cash=account.cash,
            market_value=market_value,
            equity=equity,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            total_return_pct=total_return_pct,
            order_count=len(orders),
            fill_count=len(fills),
            position_count=len(positions),
            positions=list(ordered_positions),
        )

    def current_snapshot(self, broker_id: str) -> PerformanceSnapshot:
        """Build the current snapshot from the configured reader.

        Raises :class:`PerformanceError` when no reader is configured or the
        data layer cannot supply the recorded data; the caller degrades
        gracefully instead of fabricating performance values (AIOS-208
        section 9).
        """
        if self._reader is None:
            raise PerformanceError(
                "PerformanceService requires a data reader to build a current snapshot"
            )
        try:
            account = self._reader.get_broker_account(broker_id)
            orders = list(self._reader.list_paper_orders())
            fills = list(self._reader.list_paper_fills())
            positions = list(self._reader.list_paper_positions())
        except (DataError, DatabaseError) as exc:
            raise PerformanceError(f"Could not read current performance data: {exc}") from exc
        return self.build_snapshot(
            account=account,
            orders=orders,
            fills=fills,
            positions=positions,
        )
