"""Analysis repository (AIOS-606, AIOS-402).

Analysis history is immutable: every analysis run is appended as a new record
(AIOS-505, AIOS-507). Uniqueness over (symbol, analysis_type, timeframe,
analyzed_at) prevents duplicate storage of the same run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

if TYPE_CHECKING:
    from aios.analysis.models import AnalysisResult
from aios.data.models import Timeframe
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import AnalysisResultModel
from aios.database.repositories.base import BaseRepository


def _result_key(result: "AnalysisResult") -> tuple[str, str, Timeframe, datetime]:
    """Return a dialect-independent unique key for an analysis result.

    SQLite stores naive datetimes while the domain model is UTC-aware, so
    both sides are normalized to naive UTC before comparison.
    """
    analyzed_at = result.analyzed_at
    if analyzed_at.tzinfo is not None:
        analyzed_at = analyzed_at.astimezone(timezone.utc).replace(tzinfo=None)
    return (result.symbol, result.analysis_type, result.timeframe, analyzed_at)


class AnalysisRepository(BaseRepository[AnalysisResultModel]):
    """Repository for analysis result history (AIOS-402)."""

    entity_type = AnalysisResultModel

    def add_analysis(self, results: list[AnalysisResult]) -> int:
        """Append analysis results, skipping keys already stored.

        Returns the number of newly stored rows. Historical records are
        never overwritten (AIOS-505, AIOS-507).
        """
        if not results:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            existing: set[tuple[str, str, Timeframe, datetime]] = set()
            for symbol, analysis_type, timeframe, analyzed_at in session.execute(
                select(
                    AnalysisResultModel.symbol,
                    AnalysisResultModel.analysis_type,
                    AnalysisResultModel.timeframe,
                    AnalysisResultModel.analyzed_at,
                )
            ).all():
                if analyzed_at.tzinfo is not None:
                    analyzed_at = analyzed_at.astimezone(timezone.utc).replace(tzinfo=None)
                existing.add((symbol, analysis_type, timeframe, analyzed_at))
            for result in results:
                if _result_key(result) in existing:
                    continue
                session.add(AnalysisResultModel.from_result(result))
                stored += 1
        return stored

    def get_analysis(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        analysis_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[AnalysisResult]:
        """Return analysis results for ``symbol``/``timeframe``.

        Results are ordered by ``analyzed_at`` and can be filtered by analysis
        type and time range (AIOS-402 lookup contract).
        """
        statement = (
            select(AnalysisResultModel)
            .where(
                AnalysisResultModel.symbol == symbol,
                AnalysisResultModel.timeframe == timeframe,
            )
            .order_by(AnalysisResultModel.analyzed_at)
            .limit(limit)
        )
        if analysis_type is not None:
            statement = statement.where(AnalysisResultModel.analysis_type == analysis_type)
        if start is not None:
            statement = statement.where(AnalysisResultModel.analyzed_at >= start)
        if end is not None:
            statement = statement.where(AnalysisResultModel.analyzed_at <= end)
        return [cast(AnalysisResultModel, row).to_domain() for row in self._scalars(statement)]

    def get_latest_analysis(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        analysis_type: str | None = None,
    ) -> AnalysisResult:
        """Return the most recent analysis result for ``symbol``/``timeframe``.

        Raises :class:`RecordNotFoundError` when no result exists.
        """
        statement = select(AnalysisResultModel).where(
            AnalysisResultModel.symbol == symbol,
            AnalysisResultModel.timeframe == timeframe,
        )
        if analysis_type is not None:
            statement = statement.where(AnalysisResultModel.analysis_type == analysis_type)
        row = self._first(statement.order_by(AnalysisResultModel.analyzed_at.desc()))
        if row is None:
            raise RecordNotFoundError(f"No analysis result for {symbol!r} on {timeframe.value}")
        return cast(AnalysisResultModel, row).to_domain()
