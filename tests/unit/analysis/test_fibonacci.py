"""Fibonacci level tests (AIOS-405 section 8, AIOS-205 section 7)."""

from __future__ import annotations

import pytest

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.fibonacci import fibonacci_levels
from aios.analysis.models import FibonacciLevelType

pytestmark = pytest.mark.unit


class TestFibonacciLevels:
    def test_documented_retracement_levels(self) -> None:
        result = fibonacci_levels(100.0, 80.0)
        retracements = {
            level.ratio: level.price
            for level in result.levels
            if level.level_type is FibonacciLevelType.RETRACEMENT
        }
        expected = {
            0.236: 95.28,
            0.382: 92.36,
            0.500: 90.0,
            0.618: 87.64,
            0.786: 84.28,
        }
        assert retracements == pytest.approx(expected)

    def test_default_level_types(self) -> None:
        result = fibonacci_levels(100.0, 80.0)
        retracements = [
            level for level in result.levels if level.level_type is FibonacciLevelType.RETRACEMENT
        ]
        extensions = [
            level for level in result.levels if level.level_type is FibonacciLevelType.EXTENSION
        ]
        assert [level.ratio for level in retracements] == [0.236, 0.382, 0.5, 0.618, 0.786]
        assert [level.ratio for level in extensions] == [1.272, 1.618]

    def test_custom_ratios(self) -> None:
        result = fibonacci_levels(100.0, 90.0, retracement_ratios=[0.5], extension_ratios=[])
        assert len(result.levels) == 1
        assert result.levels[0].price == pytest.approx(95.0)

    def test_invalid_pivot_order_rejected(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            fibonacci_levels(80.0, 100.0)

    def test_equal_pivots_rejected(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            fibonacci_levels(80.0, 80.0)

    def test_zero_ratio_rejected(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            fibonacci_levels(100.0, 80.0, retracement_ratios=[0.0])
