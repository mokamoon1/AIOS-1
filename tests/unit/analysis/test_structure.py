"""Market structure tests (AIOS-205 section 5, AIOS-405 section 7)."""

from __future__ import annotations

import pytest

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.models import SwingPoint, SwingType, TrendDirection
from aios.analysis.structure import classify_structure, find_swings, market_structure

pytestmark = pytest.mark.unit


def _swing(index: int, price: float, swing_type: SwingType) -> SwingPoint:
    return SwingPoint(index=index, price=price, swing_type=swing_type)


class TestFindSwings:
    def test_sawtooth_uptrend(self) -> None:
        swings = find_swings([1.0, 3.0, 2.0, 4.0, 3.0, 5.0], left=1, right=1)
        assert [(s.price, s.swing_type) for s in swings] == [
            (3.0, SwingType.HIGH),
            (2.0, SwingType.LOW),
            (4.0, SwingType.HIGH),
            (3.0, SwingType.LOW),
        ]

    def test_ties_are_ignored(self) -> None:
        assert find_swings([2.0, 2.0, 2.0]) == []

    def test_short_series_returns_empty(self) -> None:
        assert find_swings([1.0, 2.0]) == []

    def test_invalid_lookback_rejected(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            find_swings([1.0, 2.0, 3.0], left=0)
        with pytest.raises(InvalidAnalysisError):
            find_swings([1.0, 2.0, 3.0], right=-1)


class TestClassifyStructure:
    def test_higher_highs_uptrend(self) -> None:
        result = classify_structure(
            [_swing(1, 2.0, SwingType.HIGH), _swing(3, 4.0, SwingType.HIGH)]
        )
        assert result.direction is TrendDirection.UPTREND
        assert result.sequence == ["HH"]
        assert result.strength == pytest.approx(1.0)

    def test_lower_highs_downtrend(self) -> None:
        result = classify_structure(
            [_swing(1, 6.0, SwingType.HIGH), _swing(3, 4.0, SwingType.HIGH)]
        )
        assert result.direction is TrendDirection.DOWNTREND
        assert result.sequence == ["LH"]

    def test_higher_lows_uptrend(self) -> None:
        result = classify_structure([_swing(1, 2.0, SwingType.LOW), _swing(3, 5.0, SwingType.LOW)])
        assert result.direction is TrendDirection.UPTREND
        assert result.sequence == ["HL"]

    def test_tied_labels_reports_range(self) -> None:
        result = classify_structure(
            [
                _swing(1, 10.0, SwingType.HIGH),
                _swing(3, 11.0, SwingType.HIGH),
                _swing(5, 9.0, SwingType.LOW),
                _swing(7, 7.0, SwingType.LOW),
            ]
        )
        assert result.direction is TrendDirection.RANGE
        assert result.sequence == ["HH", "LL"]
        assert result.strength == pytest.approx(0.5)

    def test_empty_swings_reports_range(self) -> None:
        result = classify_structure([])
        assert result.direction is TrendDirection.RANGE
        assert result.strength == 0.0
        assert result.sequence == []


class TestMarketStructure:
    def test_uptrend_series(self) -> None:
        result = market_structure([1.0, 3.0, 2.0, 4.0, 3.0, 5.0], left=1, right=1)
        assert result.direction is TrendDirection.UPTREND
        assert result.swings

    def test_downtrend_series(self) -> None:
        result = market_structure([5.0, 3.0, 4.0, 2.0, 3.0, 1.0], left=1, right=1)
        assert result.direction is TrendDirection.DOWNTREND
        assert result.swings
