"""Strategy Evaluator - Core evaluation engine for backtest results (Phase 9.6)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import numpy as np

from aios.backtest.models import (
    BacktestResult,
    EquityPoint,
    PaperFill,
    PerformanceSnapshot,
    RiskMetrics,
    StrategyClassification,
    StrategyEvaluationResult,
    StrategyScore,
)
from aios.config import load_settings


class StrategyEvaluator:
    """Evaluates a backtest result and computes comprehensive metrics."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._eval_settings = self._settings.strategy_evaluation

    def evaluate(self, backtest_result: BacktestResult) -> StrategyEvaluationResult:
        """Evaluate a backtest result comprehensively."""
        warnings: list[str] = []

        # Validate minimum data requirements
        if len(backtest_result.equity_curve) < 2:
            warnings.append("Insufficient equity curve data for evaluation")

        if not backtest_result.fills:
            warnings.append("No fills found in backtest result")

        # Compute additional metrics from raw data
        extended_performance = self._compute_extended_performance(backtest_result)
        extended_risk = self._compute_extended_risk(backtest_result)

        # Statistical validation
        stat_validation = self._validate_statistics(backtest_result)
        if stat_validation:
            warnings.extend(stat_validation.warnings)

        # Scoring
        score = self._compute_score(
            backtest_result, extended_performance, extended_risk, stat_validation
        )

        # Classification
        classification = self._classify(score, stat_validation, backtest_result)

        return StrategyEvaluationResult(
            backtest_id=backtest_result.config.id
            if hasattr(backtest_result.config, "id")
            else UUID(int=0),
            performance=extended_performance,
            risk_metrics=extended_risk,
            statistical_validation=stat_validation,
            score=score,
            classification=classification,
            warnings=warnings,
        )

    def _compute_extended_performance(
        self, result: BacktestResult
    ) -> PerformanceSnapshot:
        """Compute extended performance metrics from raw equity curve and fills."""
        perf = result.performance

        # All core metrics are already in PerformanceSnapshot from Phase 9.5
        # This method can add any additional derived metrics if needed
        return perf

    def _compute_extended_risk(
        self, result: BacktestResult
    ) -> RiskMetrics:
        """Compute extended risk metrics."""
        return result.risk_metrics

    def _validate_statistics(
        self, result: BacktestResult
    ) -> Any:
        """Run statistical validation on the backtest result."""
        from aios.backtest.evaluation.validation import StatisticalValidator

        validator = StatisticalValidator(self._eval_settings)
        return validator.validate(result)

    def _compute_score(
        self,
        result: BacktestResult,
        performance: PerformanceSnapshot,
        risk_metrics: RiskMetrics,
        stat_validation: Any,
    ) -> StrategyScore:
        """Compute multi-dimensional strategy score."""
        from aios.backtest.evaluation.scoring import StrategyScorer

        scorer = StrategyScorer(self._settings.strategy_scoring)
        return scorer.score(result, performance, risk_metrics, stat_validation)

    def _classify(
        self,
        score: StrategyScore,
        stat_validation: Any,
        result: BacktestResult,
    ) -> StrategyClassification:
        """Classify strategy based on score and blocking conditions."""
        from aios.backtest.evaluation.classification import StrategyClassifier

        classifier = StrategyClassifier(self._settings.strategy_classification)
        return classifier.classify(score, stat_validation, result)