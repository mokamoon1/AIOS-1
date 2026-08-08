"""Paper fill repository (AIOS-606, AIOS-101 section 4.6).

Fills are immutable historical records appended for every explicit fill and
never overwritten (AIOS-402 section 11), providing the recorded data used by
performance tracking (AIOS-308 section 12).
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import select

from aios.brokers.models import PaperFill
from aios.database.engine import session_scope
from aios.database.models import PaperFillModel
from aios.database.repositories.base import BaseRepository


class PaperFillRepository(BaseRepository[PaperFillModel]):
    """Repository for recorded paper fills (AIOS-101 section 4.6)."""

    entity_type = PaperFillModel

    def add_fill(self, fill: PaperFill) -> PaperFill:
        """Append a recorded paper fill (immutable history)."""
        with session_scope(self._session_factory) as session:
            model = PaperFillModel.from_fill(fill)
            session.add(model)
            session.flush()
            return model.to_domain()

    def list_fills(self, *, order_id: str | None = None) -> list[PaperFill]:
        """Return recorded fills, optionally filtered by ``order_id``."""
        statement = select(PaperFillModel).order_by(PaperFillModel.filled_at)
        if order_id is not None:
            statement = statement.where(PaperFillModel.order_id == order_id)
        return [cast(PaperFillModel, row).to_domain() for row in self._scalars(statement)]
