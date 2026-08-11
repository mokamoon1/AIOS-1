"""Strategy Scoring (Phase 9.6)."""

from __future__ import annotations

from typing import Any

import numpy as np

from aios.backtest.models import (
    BacktestResult,
    PerformanceSnapshot,
    RiskMetrics,
    StrategyScore,
    StatisticalValidationResult,
)
from aios.backtest.evaluation.benchmark import BenchmarkResult
from aios.config import load_settings


class StrategyScorer:
    """Computes multi-dimensional strategy score."""

    def __init__(self, settings: Any | None = None) -> None:
        if settings is None:
            self._settings = load_settings()
            self._scoring = self._settings.strategy_scoring
        elif hasattr(settings, 'strategy_scoring'):
            # settings is AppSettings
            self._settings = settings
            self._scoring = settings.strategy_scoring
        else:
            # settings is already StrategyScoringSettings
            self._scoring = settings

    def score(
        self,
        result: BacktestResult,
        performance: PerformanceSnapshot,
        risk_metrics: RiskMetrics,
        stat_validation: StatisticalValidationResult | None,
        benchmark: BenchmarkResult | None = None,
    ) -> StrategyScore:
        """Compute comprehensive strategy score."""
        # Component scores (0-100)
        return_score = self._score_return(performance)
        risk_score = self._score_risk(performance, risk_metrics)
        consistency_score = self._score_consistency(performance)
        robustness_score = self._score_robustness(performance)
        oos_score = self._score_oos(result)
        statistical_score = self._score_statistical(stat_validation)
        benchmark_score = self._score_benchmark(performance, benchmark)

        # Weighted total
        weights = {
            "return": self._scoring.return_weight,
            "risk": self._scoring.risk_weight,
            "consistency": self._scoring.consistency_weight,
            "robustness": self._scoring.robustness_weight,
            "oos": self._scoring.oos_weight,
            "statistical": self._scoring.statistical_weight,
            "benchmark": self._scoring.benchmark_weight,
        }

        total = (
            return_score * weights["return"]
            + risk_score * weights["risk"]
            + consistency_score * weights["consistency"]
            + robustness_score * weights["robustness"]
            + oos_score * weights["oos"]
            + statistical_score * weights["statistical"]
            + benchmark_score * weights["benchmark"]
        )

        breakdown = {
            "return": return_score,
            "risk": risk_score,
            "consistency": consistency_score,
            "robustness": robustness_score,
            "oos": oos_score,
            "statistical": statistical_score,
            "benchmark": benchmark_score,
        }

        return StrategyScore(
            return_score=return_score,
            risk_score=risk_score,
            consistency_score=consistency_score,
            robustness_score=robustness_score,
            oos_score=oos_score,
            statistical_score=statistical_score,
            benchmark_score=benchmark_score,
            total_score=total,
            breakdown=breakdown,
        )

    def _score_return(self, perf: PerformanceSnapshot) -> float:
        """Score based on return metrics (0-100)."""
        # CAGR scoring: 15%+ = 100, 0% = 50, -10% = 0
        cagr_score = np.clip(50 + perf.cagr * 1000 / 3, 0, 100)

        # Total return scoring
        total_score = np.clip(50 + perf.total_return * 500, 0, 100)

        return (cagr_score + total_score) / 2

    def _score_risk(self, perf: PerformanceSnapshot, risk: RiskMetrics) -> float:
        """Score based on risk metrics (0-100). Lower risk = higher score."""
        # Drawdown scoring: 0% DD = 100, 20% DD = 50, 50% DD = 0
        dd_score = np.clip(100 - perf.max_drawdown * 250, 0, 100)

        # VaR scoring (lower VaR = better)
        var_95 = abs(risk.var_95)
        var_score = np.clip(100 - var_95 * 5000, 0, 100)

        # Calmar ratio: higher = better
        calmar_score = np.clip(perf.calmar_ratio * 20, 0, 100)

        return (dd_score + var_score + calmar_score) / 3

    def _score_consistency(self, perf: PerformanceSnapshot) -> float:
        """Score based on consistency metrics."""
        # Win rate: 50% = 50, 60% = 70, 70%+ = 100
        win_score = np.clip(perf.win_rate * 150, 0, 100)

        # Profit factor: 1.0 = 50, 1.5 = 75, 2.0+ = 100
        pf_score = np.clip(perf.profit_factor * 50, 0, 100)

        # Sharpe: 1.0 = 50, 1.5 = 75, 2.0+ = 100
        sharpe_score = np.clip(perf.sharpe_ratio * 50, 0, 100)

        # Sortino
        sortino_score = np.clip(perf.sortino_ratio * 50, 0, 100)

        return (win_score + pf_score + sharpe_score + sortino_score) / 4

    def _score_robustness(self, perf: PerformanceSnapshot) -> float:
        """Score based on robustness indicators."""
        # Recovery time: faster = better
        if perf.recovery_time_days > 0:
            recovery_score = np.clip(100 - perf.recovery_time_days * 2, 0, 100)
        else:
            recovery_score = 100

        # Average drawdown
        avg_dd_score = np.clip(100 - perf.avg_drawdown * 500, 0, 100)

        # Max consecutive losses
        # This would need to come from risk metrics
        return (recovery_score + avg_dd_score) / 2

    def _score_oos(self, result: BacktestResult) -> float:
        """Score based on out-of-sample performance."""
        # Check if OOS validation exists
        if hasattr(result, "evaluation") and result.evaluation:
            eval_result = result.evaluation
            if eval_result.oos_validation and eval_result.oos_validation.is_valid:
                return 100.0
            elif eval_result.oos_validation:
                return 0.0
        # No OOS data = neutral
        return 50.0

    def _score_statistical(
        self, stat_validation: StatisticalValidationResult | None
    ) -> float:
        """Score based on statistical validation."""
        if stat_validation is None:
            return 50.0

        if not stat_validation.sufficient_sample:
            return 25.0

        if not stat_validation.is_statistically_significant:
            return 40.0

        # Check warnings
        warning_penalty = min(len(stat_validation.warnings) * 5, 30)
        return max(70 - warning_penalty, 50)

    def _score_benchmark(
        self, perf: PerformanceSnapshot, benchmark: BenchmarkResult | None
    ) -> float:
        """Score based on benchmark outperformance."""
        if benchmark is None:
            return 50.0

        excess = benchmark.excess_return
        if excess > 0.05:  # 5%+ outperformance
            return 100.0
        elif excess > 0:
            return 75.0
        elif excess > -0.05:
            return 50.0
        else:
            return 25.0