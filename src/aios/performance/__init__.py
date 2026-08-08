"""AIOS Performance Tracking module (AIOS-308, AIOS-603 section 10).

Responsible for objective performance evaluation of the paper-trading
portfolio from recorded orders, fills, positions, and account data. The
module computes arithmetic metrics only; it does not execute trades and does
not invent benchmarks or thresholds (AIOS-208 section 9).
"""

from __future__ import annotations

from aios.performance.exceptions import PerformanceError
from aios.performance.service import PerformanceDataReader, PerformanceService

__all__ = [
    "PerformanceDataReader",
    "PerformanceError",
    "PerformanceService",
]
