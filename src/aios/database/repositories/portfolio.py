"""Portfolio repository (AIOS-606, AIOS-402).

The ``portfolio_positions`` table tracks current holdings (AIOS-402
section 8). The current-position view is updated in place when a holding
changes; ``updated_at`` records the last change so allocation changes remain
traceable (AIOS-206 section 8). Historical position performance is future
phase scope (AIOS-501 section 5.4).
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import select

from aios.data.models import PortfolioPosition, PositionStatus
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import PortfolioPositionModel
from aios.database.repositories.base import BaseRepository


class PortfolioRepository(BaseRepository[PortfolioPositionModel]):
    """Repository for current portfolio holdings (AIOS-402)."""

    entity_type = PortfolioPositionModel

    def upsert_position(self, position: PortfolioPosition) -> PortfolioPosition:
        """Insert or update the current position for ``symbol``/``exchange``.

        Returns the stored domain model. Updating replaces the current
        holding values in place and records the new ``updated_at``
        (AIOS-206 section 8).
        """
        with session_scope(self._session_factory) as session:
            model = session.scalars(
                select(PortfolioPositionModel).where(
                    PortfolioPositionModel.symbol == position.symbol,
                    PortfolioPositionModel.exchange == position.exchange,
                )
            ).first()
            if model is None:
                model = PortfolioPositionModel.from_position(position)
                session.add(model)
            else:
                model.quantity = position.quantity
                model.entry_price = position.entry_price
                model.current_price = position.current_price
                model.allocation = position.allocation
                model.sector = position.sector
                model.status = position.status
                model.updated_at = position.updated_at
            session.flush()
            return model.to_domain()

    def get_position(self, symbol: str, exchange: str) -> PortfolioPosition:
        """Return the current position for ``symbol``/``exchange``.

        Raises :class:`RecordNotFoundError` when no position is stored.
        """
        statement = select(PortfolioPositionModel).where(
            PortfolioPositionModel.symbol == symbol,
            PortfolioPositionModel.exchange == exchange,
        )
        row = self._first(statement)
        if row is None:
            raise RecordNotFoundError(f"No portfolio position for {symbol!r} on {exchange!r}")
        return cast(PortfolioPositionModel, row).to_domain()

    def list_positions(self, *, status: PositionStatus | None = None) -> list[PortfolioPosition]:
        """Return portfolio positions, optionally filtered by status."""
        statement = select(PortfolioPositionModel).order_by(PortfolioPositionModel.symbol)
        if status is not None:
            statement = statement.where(PortfolioPositionModel.status == status)
        return [cast(PortfolioPositionModel, row).to_domain() for row in self._scalars(statement)]

    def get_positions_by_sector(self, sector: str) -> list[PortfolioPosition]:
        """Return the open positions classified under ``sector`` (AIOS-306 section 6)."""
        statement = (
            select(PortfolioPositionModel)
            .where(
                PortfolioPositionModel.sector == sector,
                PortfolioPositionModel.status == PositionStatus.OPEN,
            )
            .order_by(PortfolioPositionModel.symbol)
        )
        return [cast(PortfolioPositionModel, row).to_domain() for row in self._scalars(statement)]
