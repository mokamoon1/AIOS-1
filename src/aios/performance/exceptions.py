"""Performance module exceptions (AIOS-308, AIOS-603 section 10).

Performance computation failures — missing data sources — are raised as
:class:`PerformanceError` so callers can degrade safely without fabricating
performance values (AIOS-208 section 9).
"""

from __future__ import annotations


class PerformanceError(Exception):
    """Base class for Performance Tracking module errors."""
