"""Standardized analysis domain models (AIOS-405, AIOS-305, AIOS-203/204/205).

The Analysis Layer consumes the standardized Data Layer models and produces
standardized analysis models consumed by engines (AIOS-605 section 12). The
models below cover the technical analysis outputs mandated by AIOS-405 and
AIOS-205: market structure (sections 5-7), Fibonacci levels (section 8), and
indicator values (section 10), plus the configurable weighted scoring
framework required by AIOS-305 section 7.

These models carry no persistence concerns; analysis history storage lives in
the Database Layer (AIOS-606).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aios.data.models import Timeframe


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketBias(str, Enum):
    """Overall market bias (AIOS-405 section 3, AIOS-203 section 4)."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class TrendDirection(str, Enum):
    """Detected price-structure direction (AIOS-205 section 5)."""

    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGE = "range"


class SwingType(str, Enum):
    """Classification of a swing point (AIOS-405 section 7)."""

    HIGH = "high"
    LOW = "low"


class SwingPoint(BaseModel):
    """A single swing (pivot) high or low in a price series.

    ``index`` locates the bar within the analyzed series and ``price`` is the
    bar's extreme value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(ge=0)
    price: float = Field(gt=0)
    swing_type: SwingType


class MarketStructure(BaseModel):
    """Market structure assessment (AIOS-205 section 5, AIOS-405 section 7).

    ``direction`` is the detected trend, ``strength`` is the fraction of
    structure classifications consistent with that direction (0.0 to 1.0),
    ``swings`` lists the identified swing points, and ``sequence`` records the
    higher-high/lower-low label for each consecutive swing pair (for example
    ``["HH", "HL"]``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    direction: TrendDirection
    strength: float = Field(ge=0.0, le=1.0)
    swings: list[SwingPoint] = Field(default_factory=list)
    sequence: list[str] = Field(default_factory=list)


class FibonacciLevelType(str, Enum):
    """Classification of a Fibonacci level (AIOS-405 section 8)."""

    RETRACEMENT = "retracement"
    EXTENSION = "extension"


class FibonacciLevel(BaseModel):
    """A single Fibonacci level with its price (AIOS-405 section 8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ratio: float = Field(gt=0)
    price: float = Field(gt=0)
    level_type: FibonacciLevelType


class FibonacciLevels(BaseModel):
    """Retracement and extension levels computed between two pivots.

    ``pivot_high`` and ``pivot_low`` delimit the analyzed range and ``levels``
    lists the computed retracement and extension prices (AIOS-405 section 8).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pivot_high: float = Field(gt=0)
    pivot_low: float = Field(gt=0)
    levels: list[FibonacciLevel] = Field(default_factory=list)

    @field_validator("pivot_high", "pivot_low")
    @classmethod
    def must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("pivot price must be positive")
        return value


class MacdResult(BaseModel):
    """MACD series aligned with the input closes (AIOS-205 section 9).

    Every list has the same length as the analyzed close series; positions
    without enough data are ``None``. ``histogram`` equals ``macd_line`` minus
    ``signal_line``.
    """

    model_config = ConfigDict(extra="forbid")

    macd_line: list[float | None] = Field(default_factory=list)
    signal_line: list[float | None] = Field(default_factory=list)
    histogram: list[float | None] = Field(default_factory=list)


class BollingerBandsResult(BaseModel):
    """Bollinger Bands series aligned with the input closes (AIOS-205 section 9)."""

    model_config = ConfigDict(extra="forbid")

    upper: list[float | None] = Field(default_factory=list)
    middle: list[float | None] = Field(default_factory=list)
    lower: list[float | None] = Field(default_factory=list)


class ScoreComponent(BaseModel):
    """A named sub-score with a configurable weight (AIOS-305 section 7).

    Weights are configurable by design; the scoring function normalizes the
    weight set before combining component scores.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value.strip()


class WeightedScore(BaseModel):
    """Result of combining component scores with configurable weights.

    ``overall`` is the weighted average of the component scores normalized by
    the total weight, so the value always lies in the closed interval 0.0 to
    1.0.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    components: list[ScoreComponent] = Field(default_factory=list)
    overall: float = Field(ge=0.0, le=1.0)


class AnalysisSnapshot(BaseModel):
    """A point-in-time analysis of one security on one timeframe.

    Carries the standardized inputs every analysis consumes: the symbol, the
    analyzed timeframe, the number of bars, and the timestamp of the analysis
    (AIOS-305 section 8).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: Timeframe
    bars: int = Field(ge=0)
    analyzed_at: datetime = Field(default_factory=_utc_now)

    @field_validator("symbol")
    @classmethod
    def symbol_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be empty")
        return value.strip()


class AnalysisResult(BaseModel):
    """A persisted analysis output (AIOS-402 table ``analysis_results``).

    Records one analysis run: the symbol, the analysis type that produced it,
    the analyzed timeframe, the resulting score (0.0 to 1.0), a short result
    label, the full detail payload, and the analysis moment. History is
    immutable: the Database Layer appends rows and never overwrites them
    (AIOS-505, AIOS-507).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    analysis_type: str
    timeframe: Timeframe = Timeframe.ONE_DAY
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    result: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    analyzed_at: datetime = Field(default_factory=_utc_now)

    @field_validator("symbol", "analysis_type")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()
