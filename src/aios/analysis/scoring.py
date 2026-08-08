"""Configurable weighted scoring (AIOS-305 section 7, AIOS-405 section 12).

AIOS combines market, fundamental, technical, and risk scores into an overall
evaluation, and the weights must be configurable (AIOS-305 section 7). This
module provides the mechanics: a score component (name, 0.0-1.0 score,
weight) and a weighted combination that normalizes the weight set before
combining. No weights are hard-coded here; callers supply the weights from
configuration or a documented model.
"""

from __future__ import annotations

from collections.abc import Sequence

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.models import ScoreComponent, WeightedScore


def weighted_score(components: Sequence[ScoreComponent]) -> WeightedScore:
    """Combine ``components`` into a normalized weighted score.

    The overall score is the weighted average of the component scores divided
    by the total weight, so it always lies in the closed interval 0.0 to 1.0.

    Raises:
        InvalidAnalysisError: if ``components`` is empty or its total weight
            is not positive.
    """
    if not components:
        raise InvalidAnalysisError("At least one score component is required")
    total_weight = sum(component.weight for component in components)
    if total_weight <= 0:
        raise InvalidAnalysisError("Total component weight must be positive")
    overall = sum(component.score * component.weight for component in components) / total_weight
    return WeightedScore(components=list(components), overall=overall)
