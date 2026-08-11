"""Strategy Classification (Phase 9.6)."""

from __future__ import annotations

from typing import Any

from aios.backtest.models import (
    StrategyClassification,
    StrategyScore,
    StatisticalValidationResult,
)
from aios.config import load_settings


class StrategyClassifier:
    """Classifies strategies based on score and blocking conditions."""

    def __init__(self, settings: Any | None = None) -> None:
        if settings is None:
            self._settings = load_settings()
            self._class_settings = self._settings.strategy_classification
        elif hasattr(settings, 'strategy_classification'):
            # settings is AppSettings
            self._settings = settings
            self._class_settings = settings.strategy_classification
        else:
            # settings is already StrategyClassificationSettings
            self._class_settings = settings

    def classify(
        self,
        score: StrategyScore,
        stat_validation: StatisticalValidationResult | None,
        result: Any,
    ) -> StrategyClassification:
        """Classify strategy based on score and blocking conditions."""
        # Check blocking conditions first
        if self._check_blocking_conditions(score, stat_validation, result):
            return StrategyClassification.FAIL

        # Score-based classification
        total = score.total_score

        if total >= self._class_settings.acceptable_threshold:
            return StrategyClassification.ROBUST
        elif total >= self._class_settings.weak_threshold:
            return StrategyClassification.ACCEPTABLE
        elif total >= self._class_settings.fail_threshold:
            return StrategyClassification.WEAK
        else:
            return StrategyClassification.FAIL

    def _check_blocking_conditions(
        self,
        score: StrategyScore,
        stat_validation: StatisticalValidationResult | None,
        result: Any,
    ) -> bool:
        """Check if any blocking conditions are triggered."""
        # OOS failure
        if self._class_settings.block_on_oos_failure:
            if hasattr(result, "evaluation") and result.evaluation:
                if result.evaluation.oos_validation and not result.evaluation.oos_validation.is_valid:
                    return True

        # Severe drawdown
        if self._class_settings.block_on_severe_drawdown:
            if score.breakdown.get("risk", 0) < 30:  # Very low risk score
                return True

        # Insufficient sample
        if self._class_settings.block_on_insufficient_sample:
            if stat_validation and not stat_validation.sufficient_sample:
                return True

        # Look-ahead
        if self._class_settings.block_on_look_ahead:
            if stat_validation:
                for w in stat_validation.warnings:
                    if "look" in w.lower() or "ahead" in w.lower():
                        return True

        # Non-deterministic
        if self._class_settings.block_on_nondeterministic:
            if stat_validation:
                for w in stat_validation.warnings:
                    if "determin" in w.lower():
                        return True

        return False