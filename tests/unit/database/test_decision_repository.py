"""Decision repository behavior tests (AIOS-606, AIOS-402, AIOS-208)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.data.models import DecisionAction, InvestmentDecision
from aios.database.exceptions import RecordNotFoundError
from aios.database.repositories import DecisionRepository

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_BASE = datetime(2026, 8, 1, 12, 0, tzinfo=_UTC)


def _decision(
    symbol: str = "AAPL",
    decision: DecisionAction = DecisionAction.WAIT,
    timestamp: datetime | None = None,
    confidence: float = 0.6,
    risk_score: float | None = 0.4,
) -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol,
        decision=decision,
        reason="aggregated analysis is incomplete",
        confidence=confidence,
        risk_score=risk_score,
        timestamp=timestamp or _BASE,
        supporting_data={"decision_score": 0.5, "risk_level": "not_evaluated"},
    )


class TestDecisionRepository:
    def test_add_and_get(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        stored = repo.add_decisions(
            [_decision(timestamp=_BASE), _decision(timestamp=_BASE + timedelta(days=1))]
        )
        assert stored == 2

        decisions = repo.get_decisions("AAPL")
        assert len(decisions) == 2
        assert decisions[0].timestamp == _BASE
        assert decisions[1].timestamp == _BASE + timedelta(days=1)

    def test_round_trip_preserves_fields(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        repo.add_decisions([_decision(decision=DecisionAction.HOLD, risk_score=0.2)])
        got = repo.get_latest_decision("AAPL")
        assert got.symbol == "AAPL"
        assert got.decision is DecisionAction.HOLD
        assert got.reason == "aggregated analysis is incomplete"
        assert got.confidence == 0.6
        assert got.risk_score == 0.2
        assert got.supporting_data == {"decision_score": 0.5, "risk_level": "not_evaluated"}

    def test_duplicate_keys_not_reinserted(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        repo.add_decisions([_decision()])
        stored = repo.add_decisions([_decision(), _decision(timestamp=_BASE + timedelta(days=1))])
        assert stored == 1
        decisions = repo.get_decisions("AAPL")
        assert len(decisions) == 2

    def test_get_decisions_filters_by_range(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        repo.add_decisions(
            [
                _decision(timestamp=_BASE),
                _decision(timestamp=_BASE + timedelta(days=1)),
                _decision(timestamp=_BASE + timedelta(days=2)),
            ]
        )
        ranged = repo.get_decisions(
            "AAPL",
            start=_BASE + timedelta(days=1),
            end=_BASE + timedelta(days=2),
        )
        assert len(ranged) == 2

    def test_get_decisions_limit(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        repo.add_decisions([_decision(timestamp=_BASE + timedelta(days=i)) for i in range(3)])
        decisions = repo.get_decisions("AAPL", limit=2)
        assert len(decisions) == 2

    def test_get_latest_returns_newest(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        repo.add_decisions(
            [
                _decision(decision=DecisionAction.WAIT, timestamp=_BASE),
                _decision(decision=DecisionAction.BUY, timestamp=_BASE + timedelta(days=1)),
            ]
        )
        latest = repo.get_latest_decision("AAPL")
        assert latest.decision is DecisionAction.BUY

    def test_get_latest_unknown_symbol_raises(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.get_latest_decision("NOPE")

    def test_add_empty(self, session_factory) -> None:
        repo = DecisionRepository(session_factory)
        assert repo.add_decisions([]) == 0
