"""AIOS Analysis Layer (AIOS-305, AIOS-405, AIOS-203/204/205).

The Analysis Layer provides the standardized computation toolkit used by the
analysis engines: standard technical indicators (AIOS-205 section 9), market
structure detection (AIOS-205 section 5), Fibonacci levels (AIOS-405 section
8), and configurable weighted scoring (AIOS-305 section 7). Engines consume
the standardized Data Layer models and produce explainable analysis using
these building blocks; no analysis here invents thresholds or trading
directions beyond the documented definitions.

Phase 9.1 adds News Intelligence models and engine for structured news analysis.
"""

from __future__ import annotations

from aios.analysis.exceptions import AnalysisError, InsufficientDataError, InvalidAnalysisError
from aios.analysis.fibonacci import (
    DEFAULT_EXTENSION_RATIOS,
    DEFAULT_RETRACEMENT_RATIOS,
    fibonacci_levels,
)
from aios.analysis.indicators import atr, bollinger_bands, ema, macd, rsi, sma
from aios.analysis.models import (
    AnalysisResult,
    AnalysisSnapshot,
    BollingerBandsResult,
    ConfidenceScore,
    Evidence,
    Explanation,
    FibonacciLevel,
    FibonacciLevels,
    FibonacciLevelType,
    MacdResult,
    MarketBias,
    MarketStructure,
    NewsIntelligenceOutput,
    RelevanceAssessment,
    ScoreComponent,
    SentimentAssessment,
    SignalDirection,
    SignalResult,
    SwingPoint,
    SwingType,
    Timeframe,
    TrendDirection,
    WeightedScore,
)
from aios.analysis.news import (
    NeutralNewsIntelligence,
    NewsArticle,
    NewsIntelligence,
    SentimentEvaluation,
    SentimentLabel,
)
from aios.analysis.news_engine import NewsEngine
from aios.analysis.scoring import weighted_score
from aios.analysis.structure import (
    classify_structure,
    find_swings,
    market_bias,
    market_structure,
)

__all__ = [
    "AnalysisError",
    "AnalysisResult",
    "AnalysisSnapshot",
    "BollingerBandsResult",
    "ConfidenceScore",
    "DEFAULT_EXTENSION_RATIOS",
    "DEFAULT_RETRACEMENT_RATIOS",
    "Evidence",
    "Explanation",
    "FibonacciLevel",
    "FibonacciLevels",
    "FibonacciLevelType",
    "InsufficientDataError",
    "InvalidAnalysisError",
    "MacdResult",
    "MarketBias",
    "MarketStructure",
    "NewsEngine",
    "NewsIntelligenceOutput",
    "NeutralNewsIntelligence",
    "NewsArticle",
    "NewsIntelligence",
    "RelevanceAssessment",
    "ScoreComponent",
    "SentimentAssessment",
    "SentimentEvaluation",
    "SentimentLabel",
    "SignalDirection",
    "SignalResult",
    "SwingPoint",
    "SwingType",
    "Timeframe",
    "TrendDirection",
    "WeightedScore",
    "atr",
    "bollinger_bands",
    "classify_structure",
    "ema",
    "fibonacci_levels",
    "find_swings",
    "macd",
    "market_bias",
    "market_structure",
    "rsi",
    "sma",
    "weighted_score",
]
