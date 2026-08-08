"""Market structure detection (AIOS-205 section 5, AIOS-405 section 7).

AIOS identifies swing highs and swing lows and classifies the price structure
as an uptrend (higher highs and higher lows), a downtrend (lower highs and
lower lows), or a range (AIOS-205 section 5). The strength value reports the
fraction of structure classifications consistent with the detected direction.
"""

from __future__ import annotations

from collections.abc import Sequence

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.models import (
    MarketBias,
    MarketStructure,
    SwingPoint,
    SwingType,
    TrendDirection,
)


def find_swings(
    closes: Sequence[float],
    *,
    left: int = 2,
    right: int = 2,
) -> list[SwingPoint]:
    """Identify swing highs and lows in ``closes``.

    A bar is a swing high when its close exceeds every other close in the
    window spanning ``left`` bars before and ``right`` bars after it, and a
    swing low when it is below every other close in the same window. Ties are
    ignored so equal-valued plateaus produce no swing.

    Raises:
        InvalidAnalysisError: if ``left`` or ``right`` is not a positive
            integer.
    """
    if not isinstance(left, int) or left < 1:
        raise InvalidAnalysisError(f"left must be a positive integer, got {left!r}")
    if not isinstance(right, int) or right < 1:
        raise InvalidAnalysisError(f"right must be a positive integer, got {right!r}")
    if len(closes) < left + right + 1:
        return []
    swings: list[SwingPoint] = []
    for i in range(left, len(closes) - right):
        window = closes[i - left : i + right + 1]
        value = closes[i]
        if value == max(window) and window.count(value) == 1:
            swings.append(SwingPoint(index=i, price=value, swing_type=SwingType.HIGH))
        elif value == min(window) and window.count(value) == 1:
            swings.append(SwingPoint(index=i, price=value, swing_type=SwingType.LOW))
    return swings


def classify_structure(swings: Sequence[SwingPoint]) -> MarketStructure:
    """Classify ``swings`` into a market structure.

    Swing highs and swing lows alternate in a price series, so the classifier
    compares consecutive swing highs (higher high ``HH`` / lower high ``LH``)
    and consecutive swing lows (higher low ``HL`` / lower low ``LL``)
    independently. The direction is the majority label: an uptrend has more
    bullish than bearish labels, a downtrend has more bearish than bullish,
    and a tie is a range. ``strength`` is the fraction of labels consistent
    with the direction.
    """
    highs = [swing for swing in swings if swing.swing_type is SwingType.HIGH]
    lows = [swing for swing in swings if swing.swing_type is SwingType.LOW]
    labels: list[str] = []
    for previous, current in zip(highs, highs[1:], strict=False):
        labels.append("HH" if current.price > previous.price else "LH")
    for previous, current in zip(lows, lows[1:], strict=False):
        labels.append("HL" if current.price > previous.price else "LL")
    bullish = sum(1 for label in labels if label in {"HH", "HL"})
    bearish = len(labels) - bullish
    if not labels:
        direction = TrendDirection.RANGE
        strength = 0.0
    elif bullish > bearish:
        direction = TrendDirection.UPTREND
        strength = bullish / len(labels)
    elif bearish > bullish:
        direction = TrendDirection.DOWNTREND
        strength = bearish / len(labels)
    else:
        direction = TrendDirection.RANGE
        strength = 0.5
    return MarketStructure(
        direction=direction,
        strength=strength,
        swings=list(swings),
        sequence=labels,
    )


def market_structure(
    closes: Sequence[float],
    *,
    left: int = 2,
    right: int = 2,
) -> MarketStructure:
    """Detect and classify the market structure of ``closes`` (AIOS-205 section 5)."""
    return classify_structure(find_swings(closes, left=left, right=right))


def market_bias(direction: TrendDirection) -> MarketBias:
    """Map a detected structure direction to the documented market bias.

    An uptrend (higher highs and higher lows) is a bullish market, a downtrend
    (lower highs and lower lows) is a bearish market, and a range is neutral
    (AIOS-205 section 5).
    """
    if direction is TrendDirection.UPTREND:
        return MarketBias.BULLISH
    if direction is TrendDirection.DOWNTREND:
        return MarketBias.BEARISH
    return MarketBias.NEUTRAL
