"""Standard technical indicator tests (AIOS-205 section 9, AIOS-405 section 10)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.indicators import atr, bollinger_bands, ema, macd, rsi, sma

pytestmark = pytest.mark.unit


class _Bar(BaseModel):
    high: float
    low: float
    close: float


def _bars(high: list[float], low: list[float], close: list[float]) -> list[_Bar]:
    return [_Bar(high=h, low=lo, close=c) for h, lo, c in zip(high, low, close, strict=False)]


class TestSma:
    def test_hand_computed_values(self) -> None:
        assert sma([1.0, 2.0, 3.0, 4.0, 5.0], 3) == [None, None, 2.0, 3.0, 4.0]

    def test_short_series_returns_none(self) -> None:
        assert sma([1.0, 2.0], 5) == [None, None]

    def test_empty_series(self) -> None:
        assert sma([], 3) == []

    def test_invalid_period(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            sma([1.0, 2.0, 3.0], 0)


class TestEma:
    def test_hand_computed_values(self) -> None:
        # period 2, multiplier 2/3, seed is the mean of the first two bars.
        assert ema([1.0, 2.0, 3.0, 4.0, 5.0], 2) == pytest.approx([None, 1.5, 2.5, 3.5, 4.5])

    def test_short_series_returns_none(self) -> None:
        assert ema([1.0, 2.0], 5) == [None, None]


class TestRsi:
    def test_published_example(self) -> None:
        # Widely published Wilder RSI example (StockCharts): first RSI = 70.46.
        closes = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
        ]
        result = rsi(closes, period=14)
        assert result[:14] == [None] * 14
        assert result[14] == pytest.approx(70.46, abs=0.01)

    def test_all_gains_reports_100(self) -> None:
        result = rsi([10.0 + i for i in range(20)], period=14)
        assert result[14] == pytest.approx(100.0)

    def test_all_losses_reports_low(self) -> None:
        result = rsi([100.0 - i for i in range(20)], period=14)
        assert result[14] == pytest.approx(0.0)

    def test_short_series_returns_none(self) -> None:
        assert rsi([1.0, 2.0, 3.0], period=14) == [None, None, None]


class TestMacd:
    def test_alignment_and_prefix(self) -> None:
        closes = [float(i) for i in range(40)]
        result = macd(closes)
        assert len(result.macd_line) == 40
        assert result.macd_line[:25] == [None] * 25
        assert result.macd_line[25] is not None

    def test_histogram_is_difference(self) -> None:
        closes = [float(i) for i in range(50)]
        result = macd(closes)
        for i in range(50):
            if result.macd_line[i] is not None and result.signal_line[i] is not None:
                assert result.histogram[i] == pytest.approx(
                    result.macd_line[i] - result.signal_line[i]
                )

    def test_trending_series_positive_histogram(self) -> None:
        result = macd([float(i * i) for i in range(60)])
        assert result.histogram[-1] is not None and result.histogram[-1] > 0

    def test_fast_period_must_be_smaller(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            macd([float(i) for i in range(30)], fast=26, slow=12)


class TestAtr:
    def test_hand_computed_values(self) -> None:
        bars = _bars(
            high=[10, 11, 12, 13, 15],
            low=[8, 8, 11, 12, 13],
            close=[9, 10, 11.5, 12.5, 14],
        )
        result = atr(bars, period=3)
        assert result[:3] == [None] * 3
        assert result[3] == pytest.approx((3 + 2 + 1.5) / 3)
        assert result[4] == pytest.approx(2.27778, abs=0.001)

    def test_short_series_returns_none(self) -> None:
        bars = _bars(high=[10, 11], low=[8, 9], close=[9, 10])
        assert atr(bars, period=14) == [None, None]


class TestBollingerBands:
    def test_hand_computed_values(self) -> None:
        result = bollinger_bands([1.0, 2.0, 3.0, 4.0, 5.0], period=3, deviations=2.0)
        assert result.middle == [None, None, 2.0, 3.0, 4.0]
        assert result.upper[2] == pytest.approx(2.0 + 2 * 0.8165, abs=0.001)
        assert result.lower[2] == pytest.approx(2.0 - 2 * 0.8165, abs=0.001)

    def test_constant_series_bands_equal_middle(self) -> None:
        result = bollinger_bands([5.0] * 25)
        for i in range(19, 25):
            assert result.upper[i] == pytest.approx(5.0)
            assert result.lower[i] == pytest.approx(5.0)

    def test_negative_deviations_rejected(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            bollinger_bands([1.0, 2.0, 3.0], deviations=-1.0)
