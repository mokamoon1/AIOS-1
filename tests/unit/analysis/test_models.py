"""Analysis domain model tests (AIOS-405, AIOS-305)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aios.analysis.models import (
    AnalysisResult,
    AnalysisSnapshot,
    FibonacciLevel,
    FibonacciLevelType,
    MarketBias,
    MarketStructure,
    SwingPoint,
    SwingType,
    Timeframe,
    TrendDirection,
    WeightedScore,
)

pytestmark = pytest.mark.unit


class TestEnums:
    def test_market_bias_values(self) -> None:
        assert MarketBias("bullish") is MarketBias.BULLISH
        assert MarketBias("bearish") is MarketBias.BEARISH
        assert MarketBias("neutral") is MarketBias.NEUTRAL

    def test_trend_direction_values(self) -> None:
        assert TrendDirection("uptrend") is TrendDirection.UPTREND
        assert TrendDirection("downtrend") is TrendDirection.DOWNTREND
        assert TrendDirection("range") is TrendDirection.RANGE


class TestMarketStructure:
    def test_constructs(self) -> None:
        structure = MarketStructure(
            direction="uptrend",
            strength=0.8,
            swings=[SwingPoint(index=2, price=10.0, swing_type=SwingType.HIGH)],
            sequence=["HH"],
        )
        assert structure.direction is TrendDirection.UPTREND
        assert structure.swings[0].swing_type is SwingType.HIGH

    def test_strength_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MarketStructure(direction="uptrend", strength=1.5)
        with pytest.raises(ValidationError):
            MarketStructure(direction="uptrend", strength=-0.1)

    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MarketStructure(direction="uptrend", strength=0.5, bogus=True)


class TestAnalysisSnapshot:
    def test_constructs_with_timeframe(self) -> None:
        snapshot = AnalysisSnapshot(symbol="AAPL", timeframe="1d", bars=50)
        assert snapshot.timeframe is Timeframe.ONE_DAY

    def test_empty_symbol_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisSnapshot(symbol=" ", timeframe="1d", bars=50)

    def test_negative_bars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisSnapshot(symbol="AAPL", timeframe="1d", bars=-1)


class TestFibonacciLevel:
    def test_level_types(self) -> None:
        retracement = FibonacciLevel(ratio=0.5, price=90.0, level_type="retracement")
        extension = FibonacciLevel(ratio=1.618, price=70.0, level_type="extension")
        assert retracement.level_type is FibonacciLevelType.RETRACEMENT
        assert extension.level_type is FibonacciLevelType.EXTENSION

    def test_zero_ratio_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FibonacciLevel(ratio=0.0, price=90.0, level_type="retracement")


class TestWeightedScoreModel:
    def test_overall_bounds(self) -> None:
        with pytest.raises(ValidationError):
            WeightedScore(components=[], overall=1.1)


class TestAnalysisResult:
    def test_constructs_with_defaults(self) -> None:
        result = AnalysisResult(symbol="AAPL", analysis_type="technical")
        assert result.timeframe is Timeframe.ONE_DAY
        assert result.score is None
        assert result.details == {}

    def test_empty_symbol_or_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisResult(symbol=" ", analysis_type="technical")
        with pytest.raises(ValidationError):
            AnalysisResult(symbol="AAPL", analysis_type="")

    def test_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisResult(symbol="AAPL", analysis_type="technical", score=1.5)
        with pytest.raises(ValidationError):
            AnalysisResult(symbol="AAPL", analysis_type="technical", score=-0.1)
