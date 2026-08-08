"""Analysis Layer exceptions (AIOS-305, AIOS-405).

These exceptions build on the unified :class:`AnalysisError` so analysis
failures remain part of the AIOS error hierarchy (AIOS-104 section 7) while
giving the analysis layer precise failure categories for invalid inputs and
insufficient data.
"""

from __future__ import annotations

from aios.errors import AnalysisError


class InvalidAnalysisError(AnalysisError):
    """Raised when an analysis computation receives invalid input.

    Analysis engines must consume verified data only (AIOS-305 section 10);
    this error stops a computation before any result is produced.
    """


class InsufficientDataError(AnalysisError):
    """Raised when an analysis computation lacks enough data points.

    Indicators and structure analysis require a minimum number of bars
    (AIOS-308 section 7); this error reports that the requirement is not
    satisfied.
    """
