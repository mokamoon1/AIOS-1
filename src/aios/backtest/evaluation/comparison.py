"""Multi-Backtest Comparison (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aios.backtest.models import (
    BacktestResult,
    StrategyClassification,
    StrategyEvaluationResult,
)
from aios.config import load_settings


class BacktestComparator:
    """Compares multiple backtest results."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()

    def compare(
        self,
        results: Sequence[tuple[str, BacktestResult]],
        evaluations: Sequence[StrategyEvaluationResult] | None = None,
    ) -> ComparisonResult:
        """Compare multiple backtest results."""
        if not results:
            return ComparisonResult(
                rankings=[],
                best_overall="",
                comparison_matrix={},
                notes=[],
            )

        # Build comparison data
        comparison_data = []
        for name, result in results:
            eval_result = None
            if evaluations:
                eval_result = next(
                    (e for e in evaluations if e.backtest_id == getattr(result.config, "id", None)),
                    None,
                )

            data = {
                "name": name,
                "result": result,
                "evaluation": eval_result,
                "perf": result.performance,
            }
            comparison_data.append(data)

        # Rank by total score if evaluations available, else by Sharpe
        if evaluations and all(d["evaluation"] and d["evaluation"].score for d in comparison_data):
            comparison_data.sort(key=lambda d: d["evaluation"].score.total_score, reverse=True)
        else:
            comparison_data.sort(key=lambda d: d["perf"].sharpe_ratio, reverse=True)

        rankings = [d["name"] for d in comparison_data]

        # Build comparison matrix
        matrix = self._build_matrix(comparison_data)

        # Notes
        notes = self._generate_notes(comparison_data)

        return ComparisonResult(
            rankings=rankings,
            best_overall=rankings[0] if rankings else "",
            comparison_matrix=matrix,
            notes=notes,
        )

    def _build_matrix(
        self, data: list[dict[str, Any]]
    ) -> dict[str, dict[str, float]]:
        """Build comparison matrix of key metrics."""
        metrics = [
            "total_return",
            "cagr",
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "total_trades",
        ]

        matrix = {}
        for d in data:
            name = d["name"]
            perf = d["perf"]
            matrix[name] = {}
            for m in metrics:
                matrix[name][m] = getattr(perf, m, 0.0)

        return matrix

    def _generate_notes(self, data: list[dict[str, Any]]) -> list[str]:
        """Generate comparison notes."""
        notes = []

        if len(data) < 2:
            return ["Only one strategy to compare"]

        best = data[0]
        worst = data[-1]

        notes.append(
            f"Best: {best['name']} (Sharpe: {best['perf'].sharpe_ratio:.2f})"
        )
        notes.append(
            f"Worst: {worst['name']} (Sharpe: {worst['perf'].sharpe_ratio:.2f})"
        )

        # Check for significant differences
        best_sharpe = best["perf"].sharpe_ratio
        worst_sharpe = worst["perf"].sharpe_ratio
        if best_sharpe - worst_sharpe > 0.5:
            notes.append(
                f"Significant Sharpe difference: {best_sharpe:.2f} vs {worst_sharpe:.2f}"
            )

        # Drawdown comparison
        best_dd = best["perf"].max_drawdown
        worst_dd = worst["perf"].max_drawdown
        if worst_dd - best_dd > 0.1:
            notes.append(
                f"Drawdown spread: {best_dd:.1%} to {worst_dd:.1%}"
            )

        return notes


class ComparisonResult:
    """Result of multi-backtest comparison."""

    def __init__(
        self,
        rankings: list[str],
        best_overall: str,
        comparison_matrix: dict[str, dict[str, float]],
        notes: list[str],
    ) -> None:
        self.rankings = rankings
        self.best_overall = best_overall
        self.comparison_matrix = comparison_matrix
        self.notes = notes