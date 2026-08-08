"""Paper position repository (AIOS-606, AIOS-407, AIOS-603 section 11).

The broker-side holdings view is updated in place after each fill so the
broker module can synchronize positions (AIOS-603 section 11).
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import select

from aios.brokers.models import BrokerPosition
from aios.database.engine import session_scope
from aios.database.models import PaperPositionModel
from aios.database.repositories.base import BaseRepository


class PaperPositionRepository(BaseRepository[PaperPositionModel]):
    """Repository for current paper positions (AIOS-407)."""

    entity_type = PaperPositionModel

    def upsert_position(self, position: BrokerPosition) -> BrokerPosition:
        """Insert or update the current paper position for symbol/exchange."""
        with session_scope(self._session_factory) as session:
            model = session.scalars(
                select(PaperPositionModel).where(
                    PaperPositionModel.symbol == position.symbol,
                    PaperPositionModel.exchange == position.exchange,
                )
            ).first()
            if model is None:
                model = PaperPositionModel.from_position(position)
                session.add(model)
            else:
                model.quantity = position.quantity
                model.entry_price = position.entry_price
                model.current_price = position.current_price
                model.market_value = position.market_value
                model.unrealized_pnl = position.unrealized_pnl
                model.realized_pnl = position.realized_pnl
                model.updated_at = position.updated_at
            session.flush()
            return model.to_domain()

    def list_positions(self) -> list[BrokerPosition]:
        """Return the current paper positions in symbol order."""
        statement = select(PaperPositionModel).order_by(PaperPositionModel.symbol)
        return [cast(PaperPositionModel, row).to_domain() for row in self._scalars(statement)]
