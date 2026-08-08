"""Fibonacci retracement and extension levels (AIOS-405 section 8).

The Technical Analysis Engine calculates retracement and extension levels
between a swing high and a swing low. The documented retracement ratios are
0.236, 0.382, 0.500, 0.618, and 0.786 (AIOS-405 section 8, AIOS-205 section
7); the extension ratios default to the industry-standard 1.272 and 1.618 and
are configurable.
"""

from __future__ import annotations

from collections.abc import Sequence

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.models import FibonacciLevel, FibonacciLevels, FibonacciLevelType

DEFAULT_RETRACEMENT_RATIOS: tuple[float, ...] = (0.236, 0.382, 0.500, 0.618, 0.786)
DEFAULT_EXTENSION_RATIOS: tuple[float, ...] = (1.272, 1.618)


def fibonacci_levels(
    pivot_high: float,
    pivot_low: float,
    *,
    retracement_ratios: Sequence[float] = DEFAULT_RETRACEMENT_RATIOS,
    extension_ratios: Sequence[float] = DEFAULT_EXTENSION_RATIOS,
) -> FibonacciLevels:
    """Compute Fibonacci levels between ``pivot_high`` and ``pivot_low``.

    A level with ratio ``r`` sits at ``pivot_high - r * (pivot_high -
    pivot_low)``. Ratios inside the 0.0-1.0 band are retracement levels;
    ratios above 1.0 project beyond the low and are extension levels.

    Raises:
        InvalidAnalysisError: if ``pivot_high`` is not greater than
            ``pivot_low`` or a configured ratio is not positive.
    """
    if pivot_high <= pivot_low:
        raise InvalidAnalysisError(
            f"pivot_high ({pivot_high}) must be greater than pivot_low ({pivot_low})"
        )
    levels: list[FibonacciLevel] = []
    spread = pivot_high - pivot_low
    for ratio in retracement_ratios:
        if ratio <= 0:
            raise InvalidAnalysisError(f"retracement ratio must be positive, got {ratio!r}")
        levels.append(
            FibonacciLevel(
                ratio=ratio,
                price=pivot_high - ratio * spread,
                level_type=FibonacciLevelType.RETRACEMENT,
            )
        )
    for ratio in extension_ratios:
        if ratio <= 0:
            raise InvalidAnalysisError(f"extension ratio must be positive, got {ratio!r}")
        levels.append(
            FibonacciLevel(
                ratio=ratio,
                price=pivot_high - ratio * spread,
                level_type=FibonacciLevelType.EXTENSION,
            )
        )
    return FibonacciLevels(pivot_high=pivot_high, pivot_low=pivot_low, levels=levels)
