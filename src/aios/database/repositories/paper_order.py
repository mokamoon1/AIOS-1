"""Paper order repository (AIOS-606, AIOS-407).

The ``paper_orders`` table stores the paper order book. Orders are updated in
place only for the documented lifecycle transitions (AIOS-1103 section 11);
fills are appended immutably so execution history is preserved (AIOS-402
section 11).
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import select

from aios.brokers.models import OrderStatus, PaperOrder
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import PaperOrderModel
from aios.database.repositories.base import BaseRepository


class PaperOrderRepository(BaseRepository[PaperOrderModel]):
    """Repository for the paper order book (AIOS-407)."""

    entity_type = PaperOrderModel

    def add_order(self, order: PaperOrder) -> PaperOrder:
        """Append a submitted paper order (PENDING) to the order book."""
        with session_scope(self._session_factory) as session:
            model = PaperOrderModel.from_order(order)
            session.add(model)
            session.flush()
            return model.to_domain()

    def get_order(self, order_id: str) -> PaperOrder:
        """Return the paper order identified by ``order_id``.

        Raises :class:`RecordNotFoundError` when no such order is stored.
        """
        statement = select(PaperOrderModel).where(PaperOrderModel.order_id == order_id)
        row = self._first(statement)
        if row is None:
            raise RecordNotFoundError(f"No paper order with id {order_id!r}")
        return cast(PaperOrderModel, row).to_domain()

    def list_orders(self, *, status: OrderStatus | None = None) -> list[PaperOrder]:
        """Return paper orders, optionally filtered by status."""
        statement = select(PaperOrderModel).order_by(PaperOrderModel.submitted_at)
        if status is not None:
            statement = statement.where(PaperOrderModel.status == status)
        return [cast(PaperOrderModel, row).to_domain() for row in self._scalars(statement)]

    def update_order(self, order: PaperOrder) -> PaperOrder:
        """Apply a lifecycle update to an existing paper order (AIOS-1103).

        Only the state fields are replaced; the stored ``order_id`` is the
        immutable identity. Raises :class:`RecordNotFoundError` when the
        order is not stored.
        """
        with session_scope(self._session_factory) as session:
            model = session.scalars(
                select(PaperOrderModel).where(PaperOrderModel.order_id == order.order_id)
            ).first()
            if model is None:
                raise RecordNotFoundError(f"No paper order with id {order.order_id!r}")
            model.symbol = order.symbol
            model.exchange = order.exchange
            model.side = order.side
            model.quantity = order.quantity
            model.price = order.price
            model.status = order.status
            model.reason = order.reason
            model.decision_ref = order.decision_ref
            model.updated_at = order.updated_at
            session.flush()
            return model.to_domain()
