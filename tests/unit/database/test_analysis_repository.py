"""Analysis repository behavior tests (AIOS-606, AIOS-402)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.analysis.models import AnalysisResult
from aios.data.models import Timeframe
from aios.database.exceptions import RecordNotFoundError
from aios.database.repositories import AnalysisRepository

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_BASE = datetime(2026, 8, 1, 12, 0, tzinfo=_UTC)


def _result(
    symbol: str = "AAPL",
    analysis_type: str = "technical",
    analyzed_at: datetime | None = None,
    score: float = 0.8,
) -> AnalysisResult:
    return AnalysisResult(
        symbol=symbol,
        analysis_type=analysis_type,
        timeframe=Timeframe.ONE_DAY,
        score=score,
        result="bullish",
        details={"market_bias": "bullish", "bars": 250},
        analyzed_at=analyzed_at or _BASE,
    )


class TestAnalysisRepository:
    def test_add_and_get(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        stored = repo.add_analysis(
            [_result(analyzed_at=_BASE), _result(analyzed_at=_BASE + timedelta(days=1))]
        )
        assert stored == 2

        results = repo.get_analysis("AAPL", Timeframe.ONE_DAY)
        assert len(results) == 2
        assert results[0].analyzed_at == _BASE
        assert results[1].analyzed_at == _BASE + timedelta(days=1)
        assert results[0].details["market_bias"] == "bullish"

    def test_round_trip_preserves_fields(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        repo.add_analysis([_result()])
        got = repo.get_latest_analysis("AAPL", Timeframe.ONE_DAY)
        assert got.symbol == "AAPL"
        assert got.analysis_type == "technical"
        assert got.timeframe is Timeframe.ONE_DAY
        assert got.score == 0.8
        assert got.result == "bullish"
        assert got.details == {"market_bias": "bullish", "bars": 250}

    def test_duplicate_keys_not_reinserted(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        repo.add_analysis([_result()])
        stored = repo.add_analysis([_result(), _result(analyzed_at=_BASE + timedelta(days=1))])
        assert stored == 1
        results = repo.get_analysis("AAPL", Timeframe.ONE_DAY)
        assert len(results) == 2

    def test_get_analysis_filters_by_type_and_range(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        repo.add_analysis(
            [
                _result(analysis_type="market", analyzed_at=_BASE),
                _result(analysis_type="technical", analyzed_at=_BASE + timedelta(days=1)),
                _result(analysis_type="market", analyzed_at=_BASE + timedelta(days=2)),
            ]
        )
        markets = repo.get_analysis("AAPL", Timeframe.ONE_DAY, analysis_type="market")
        assert len(markets) == 2
        assert all(r.analysis_type == "market" for r in markets)

        ranged = repo.get_analysis(
            "AAPL",
            Timeframe.ONE_DAY,
            start=_BASE + timedelta(days=1),
            end=_BASE + timedelta(days=2),
        )
        assert len(ranged) == 2

    def test_get_analysis_limit(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        repo.add_analysis([_result(analyzed_at=_BASE + timedelta(days=i)) for i in range(3)])
        results = repo.get_analysis("AAPL", Timeframe.ONE_DAY, limit=2)
        assert len(results) == 2

    def test_get_latest_returns_newest(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        repo.add_analysis(
            [
                _result(analysis_type="market", analyzed_at=_BASE),
                _result(analysis_type="technical", analyzed_at=_BASE + timedelta(days=1)),
            ]
        )
        latest = repo.get_latest_analysis("AAPL", Timeframe.ONE_DAY)
        assert latest.analysis_type == "technical"

    def test_get_latest_unknown_symbol_raises(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.get_latest_analysis("NOPE", Timeframe.ONE_DAY)

    def test_add_empty(self, session_factory) -> None:
        repo = AnalysisRepository(session_factory)
        assert repo.add_analysis([]) == 0
