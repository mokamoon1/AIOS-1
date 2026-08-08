"""Standard technical indicators (AIOS-205 section 9, AIOS-405 section 10).

The Technical Analysis Engine requires trend (moving averages), momentum
(RSI, MACD), volatility (ATR, Bollinger Bands), and volume tools. This module
implements the standard mathematical definitions of those indicators with
configurable parameters.

Every indicator returns series aligned with the input: a value of ``None``
marks a position where the indicator cannot yet be computed (not enough
preceding bars). Indicators never raise on short series; they simply yield
``None`` until sufficient data is available.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.models import BollingerBandsResult, MacdResult


def _validate_period(period: int) -> None:
    if not isinstance(period, int) or period < 1:
        raise InvalidAnalysisError(f"period must be a positive integer, got {period!r}")


def _all_none(size: int) -> list[float | None]:
    return [None] * size


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Simple moving average of ``values`` over ``period`` bars.

    Each output position is the arithmetic mean of the trailing ``period``
    values; positions before ``period - 1`` are ``None``.
    """
    _validate_period(period)
    size = len(values)
    if size == 0:
        return []
    out = _all_none(size)
    for i in range(period - 1, size):
        window = values[i - period + 1 : i + 1]
        out[i] = sum(window) / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """Exponential moving average of ``values`` over ``period`` bars.

    The first computed value seeds the series with the simple average of the
    first ``period`` bars; subsequent values apply the standard multiplier
    ``2 / (period + 1)``.
    """
    _validate_period(period)
    size = len(values)
    if size < period:
        return _all_none(size)
    out = _all_none(size)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    multiplier = 2.0 / (period + 1)
    for i in range(period, size):
        out[i] = (values[i] - out[i - 1]) * multiplier + out[i - 1]  # type: ignore[operator]
    return out


def rsi(closes: Sequence[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index of ``closes`` using Wilder's smoothing.

    The first RSI value uses the average gain and average loss over the first
    ``period`` price changes; later values smooth those averages with the
    Wilder factor ``(period - 1) / period``. When average loss is zero the
    standard convention assigns RSI 100.
    """
    _validate_period(period)
    size = len(closes)
    if size < period + 1:
        return _all_none(size)
    gains: list[float] = []
    losses: list[float] = []
    previous = closes[0]
    for close in closes[1:]:
        change = close - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
        previous = close

    def to_rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0.0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    out = _all_none(size)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, size):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = to_rsi(avg_gain, avg_loss)
    return out


def macd(
    closes: Sequence[float],
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MacdResult:
    """Moving Average Convergence Divergence (AIOS-205 section 9).

    ``macd_line`` is the fast EMA minus the slow EMA, ``signal_line`` is the
    ``signal``-period EMA of ``macd_line``, and ``histogram`` is the
    difference between the two. All series are aligned with ``closes``.
    """
    _validate_period(fast)
    _validate_period(slow)
    _validate_period(signal)
    if fast >= slow:
        raise InvalidAnalysisError(f"fast period ({fast}) must be smaller than slow ({slow})")
    size = len(closes)
    if size == 0:
        return MacdResult()
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line: list[float | None] = _all_none(size)
    for i in range(size):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line[i] = fast_ema[i] - slow_ema[i]  # type: ignore[operator]
    start = 0
    while start < size and macd_line[start] is None:
        start += 1
    compact = [value for value in macd_line[start:] if value is not None]
    signal_compact = ema(compact, signal)
    signal_line: list[float | None] = _all_none(size)
    for i, value in enumerate(signal_compact):
        signal_line[start + i] = value
    histogram: list[float | None] = _all_none(size)
    for i in range(size):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]  # type: ignore[operator]
    return MacdResult(macd_line=macd_line, signal_line=signal_line, histogram=histogram)


def atr(candles: Sequence[object], period: int = 14) -> list[float | None]:
    """Average True Range of ``candles`` using Wilder's smoothing.

    Each candle provides ``high``, ``low``, and ``close`` attributes (the Data
    Layer :class:`Candle` model satisfies this contract). True range is the
    largest of the current range and the gaps to the previous close.
    """
    _validate_period(period)
    size = len(candles)
    if size < period + 1:
        return _all_none(size)
    true_ranges: list[float] = []
    previous_close = candles[0].close  # type: ignore[attr-defined]
    for candle in candles[1:]:
        high = candle.high  # type: ignore[attr-defined]
        low = candle.low  # type: ignore[attr-defined]
        close = candle.close  # type: ignore[attr-defined]
        true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = close
    out = _all_none(size)
    atr_value = sum(true_ranges[:period]) / period
    out[period] = atr_value
    for i in range(period + 1, size):
        atr_value = (atr_value * (period - 1) + true_ranges[i - 1]) / period
        out[i] = atr_value
    return out


def bollinger_bands(
    closes: Sequence[float],
    *,
    period: int = 20,
    deviations: float = 2.0,
) -> BollingerBandsResult:
    """Bollinger Bands of ``closes`` (AIOS-205 section 9).

    The middle band is the simple moving average, and the upper and lower
    bands are the middle band plus or minus ``deviations`` population standard
    deviations.
    """
    _validate_period(period)
    if deviations < 0:
        raise InvalidAnalysisError("deviations must be non-negative")
    size = len(closes)
    if size == 0:
        return BollingerBandsResult()
    middle = sma(closes, period)
    upper: list[float | None] = _all_none(size)
    lower: list[float | None] = _all_none(size)
    for i in range(period - 1, size):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / period
        std_dev = math.sqrt(variance)
        upper[i] = mean + deviations * std_dev
        lower[i] = mean - deviations * std_dev
    return BollingerBandsResult(upper=upper, middle=middle, lower=lower)
