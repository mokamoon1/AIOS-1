"""Weighted scoring tests (AIOS-305 section 7, AIOS-405 section 12)."""

from __future__ import annotations

import pytest

from aios.analysis.exceptions import InvalidAnalysisError
from aios.analysis.models import ScoreComponent
from aios.analysis.scoring import weighted_score

pytestmark = pytest.mark.unit


class TestWeightedScore:
    def test_weighted_average(self) -> None:
        result = weighted_score(
            [
                ScoreComponent(name="market", score=0.5, weight=1.0),
                ScoreComponent(name="technical", score=1.0, weight=3.0),
            ]
        )
        assert result.overall == pytest.approx(0.875)

    def test_single_component(self) -> None:
        result = weighted_score([ScoreComponent(name="technical", score=0.6, weight=1.0)])
        assert result.overall == pytest.approx(0.6)

    def test_weights_are_normalized(self) -> None:
        result = weighted_score(
            [
                ScoreComponent(name="a", score=0.0, weight=2.0),
                ScoreComponent(name="b", score=1.0, weight=2.0),
            ]
        )
        assert result.overall == pytest.approx(0.5)

    def test_empty_components_rejected(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            weighted_score([])

    def test_zero_total_weight_rejected(self) -> None:
        with pytest.raises(InvalidAnalysisError):
            weighted_score([ScoreComponent(name="a", score=0.5, weight=0.0)])


class TestScoreComponentValidation:
    def test_score_bounds(self) -> None:
        with pytest.raises(ValueError):
            ScoreComponent(name="a", score=1.5, weight=1.0)
        with pytest.raises(ValueError):
            ScoreComponent(name="a", score=-0.1, weight=1.0)

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError):
            ScoreComponent(name="a", score=0.5, weight=-1.0)

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            ScoreComponent(name=" ", score=0.5, weight=1.0)

    def test_weighted_score_overall_bounds(self) -> None:
        result = weighted_score([ScoreComponent(name="a", score=1.0, weight=1.0)])
        assert result.overall <= 1.0
        assert result.overall >= 0.0
