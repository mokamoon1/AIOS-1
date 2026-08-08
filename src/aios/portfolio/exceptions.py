"""Portfolio module exceptions (AIOS-206, AIOS-306, AIOS-603 section 10).

Portfolio computation failures — missing data sources and invalid snapshots —
are raised as :class:`PortfolioError` so callers can degrade safely without
fabricating portfolio values (AIOS-206 section 12).
"""

from __future__ import annotations


class PortfolioError(Exception):
    """Base class for Portfolio module errors (AIOS-306 section 8)."""
