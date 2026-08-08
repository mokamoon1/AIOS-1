"""Decision repository (AIOS-606, AIOS-402).

Decision history is immutable: every decision is appended as a new record and
never overwritten (AIOS-208 section 11, AIOS-505, AIOS-507). Uniqueness over
(symbol, decision, timestamp) prevents duplicate storage of the same decision
record.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select

from aios.data.models import DecisionAction, InvestmentDecision
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import InvestmentDecisionModel
from aios.database.repositories.base import BaseRepository


def _decision_key(decision: InvestmentDecision) -> tuple[str, DecisionAction, datetime]:
    """Return a dialect-independent unique key for an investment decision.

    SQLite stores naive datetimes while the domain model is UTC-aware, so
    both sides are normalized to naive UTC before comparison.
    """
    timestamp = decision.timestamp
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    return (decision.symbol, decision.decision, timestamp)


class DecisionRepository(BaseRepository[InvestmentDecisionModel]):
    """Repository for investment decision history (AIOS-402)."""

    entity_type = InvestmentDecisionModel

    def add_decisions(self, decisions: list[InvestmentDecision]) -> int:
        """Append investment decisions, skipping keys already stored.

        Returns the number of newly stored rows. Decision history is never
        overwritten (AIOS-208 section 11, AIOS-505, AIOS-507).
        """
        if not decisions:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            existing: set[tuple[str, DecisionAction, datetime]] = set()
            for symbol, decision, timestamp in session.execute(
                select(
                    InvestmentDecisionModel.symbol,
                    InvestmentDecisionModel.decision,
                    InvestmentDecisionModel.timestamp,
                )
            ).all():
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
                existing.add((symbol, decision, timestamp))
            for decision in decisions:
                if _decision_key(decision) in existing:
                    continue
                session.add(InvestmentDecisionModel.from_decision(decision))
                stored += 1
        return stored

    def get_decisions(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[InvestmentDecision]:
        """Return the decision history for ``symbol``.

        Decisions are ordered by ``timestamp`` and can be filtered by time
        range (AIOS-402 lookup contract, AIOS-208 section 11).
        """
        statement = (
            select(InvestmentDecisionModel)
            .where(InvestmentDecisionModel.symbol == symbol)
            .order_by(InvestmentDecisionModel.timestamp)
            .limit(limit)
        )
        if start is not None:
            statement = statement.where(InvestmentDecisionModel.timestamp >= start)
        if end is not None:
            statement = statement.where(InvestmentDecisionModel.timestamp <= end)
        return [cast(InvestmentDecisionModel, row).to_domain() for row in self._scalars(statement)]

    def get_latest_decision(self, symbol: str) -> InvestmentDecision:
        """Return the most recent decision for ``symbol``.

        Raises :class:`RecordNotFoundError` when no decision exists.
        """
        statement = select(InvestmentDecisionModel).where(InvestmentDecisionModel.symbol == symbol)
        row = self._first(statement.order_by(InvestmentDecisionModel.timestamp.desc()))
        if row is None:
            raise RecordNotFoundError(f"No investment decision for {symbol!r}")
        return cast(InvestmentDecisionModel, row).to_domain()
