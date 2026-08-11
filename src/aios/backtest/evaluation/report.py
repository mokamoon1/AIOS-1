"""Report Generator (Phase 9.6)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aios.backtest.models import (
    BacktestResult,
    BenchmarkResult,
    MonteCarloResult,
    OOSValidationResult,
    PerformanceSnapshot,
    RobustnessResult,
    SensitivityResult,
    StatisticalValidationResult,
    StrategyClassification,
    StrategyEvaluationResult,
    StrategyScore,
    WalkForwardResult,
)
from aios.config import load_settings


class ReportGenerator:
    """Generates comprehensive evaluation reports."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()

    def generate(self, evaluation: StrategyEvaluationResult) -> str:
        """Generate full evaluation report as markdown."""
        lines = []

        # Header
        lines.append("# AIOS Phase 9.6 Strategy Evaluation Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
        lines.append(f"**Backtest ID:** {evaluation.backtest_id}")
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(f"**Classification:** {evaluation.classification.value.upper()}")
        if evaluation.score:
            lines.append(f"**Total Score:** {evaluation.score.total_score:.1f}/100")
        lines.append("")

        # Warnings
        if evaluation.warnings:
            lines.append("### Warnings")
            for w in evaluation.warnings:
                lines.append(f"- ⚠️ {w}")
            lines.append("")

        # Performance
        lines.append("## Performance Metrics")
        lines.append("")
        self._append_performance_table(lines, evaluation.performance)
        lines.append("")

        # Risk Metrics
        lines.append("## Risk Metrics")
        lines.append("")
        self._append_risk_table(lines, evaluation.risk_metrics)
        lines.append("")

        # Benchmark
        if evaluation.benchmark:
            lines.append("## Benchmark Comparison")
            lines.append("")
            self._append_benchmark(lines, evaluation.benchmark)
            lines.append("")

        # Walk-Forward
        if evaluation.walk_forward:
            lines.append("## Walk-Forward Analysis")
            lines.append("")
            self._append_walk_forward(lines, evaluation.walk_forward)
            lines.append("")

        # OOS Validation
        if evaluation.oos_validation:
            lines.append("## Out-of-Sample Validation")
            lines.append("")
            self._append_oos(lines, evaluation.oos_validation)
            lines.append("")

        # Sensitivity
        if evaluation.sensitivity:
            lines.append("## Parameter Sensitivity")
            lines.append("")
            self._append_sensitivity(lines, evaluation.sensitivity)
            lines.append("")

        # Robustness
        if evaluation.robustness:
            lines.append("## Robustness Analysis")
            lines.append("")
            self._append_robustness(lines, evaluation.robustness)
            lines.append("")

        # Regime
        if evaluation.regime_analysis:
            lines.append("## Market Regime Analysis")
            lines.append("")
            self._append_regime(lines, evaluation.regime_analysis)
            lines.append("")

        # Monte Carlo
        if evaluation.monte_carlo:
            lines.append("## Monte Carlo Simulation")
            lines.append("")
            self._append_monte_carlo(lines, evaluation.monte_carlo)
            lines.append("")

        # Statistical Validation
        if evaluation.statistical_validation:
            lines.append("## Statistical Validation")
            lines.append("")
            self._append_statistical(lines, evaluation.statistical_validation)
            lines.append("")

        # Scoring
        if evaluation.score:
            lines.append("## Strategy Scoring")
            lines.append("")
            self._append_scoring(lines, evaluation.score)
            lines.append("")

        # Classification
        lines.append("## Strategy Classification")
        lines.append("")
        lines.append(f"**{evaluation.classification.value.upper()}**")
        lines.append("")

        # Limitations
        lines.append("## Limitations")
        lines.append("")
        lines.append(
            "This evaluation is based on historical backtest data and "
            "does not guarantee future performance. All metrics are computed "
            "from simulated trades with modeled transaction costs. "
            "Real trading may involve additional slippage, "
            "liquidity constraints, and execution risks not captured here."
        )
        lines.append("")

        return "\n".join(lines)

    def _append_performance_table(self, lines: list[str], perf: PerformanceSnapshot) -> None:
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Return | {perf.total_return:.2%} |")
        lines.append(f"| CAGR | {perf.cagr:.2%} |")
        lines.append(f"| Annualized Return | {perf.annualized_return:.2%} |")
        lines.append(f"| Sharpe Ratio | {perf.sharpe_ratio:.3f} |")
        lines.append(f"| Sortino Ratio | {perf.sortino_ratio:.3f} |")
        lines.append(f"| Calmar Ratio | {perf.calmar_ratio:.3f} |")
        lines.append(f"| Max Drawdown | {perf.max_drawdown:.2%} |")
        lines.append(f"| Avg Drawdown | {perf.avg_drawdown:.2%} |")
        lines.append(f"| Max DD Duration | {perf.max_drawdown_duration_days} days |")
        lines.append(f"| Recovery Time | {perf.recovery_time_days} days |")
        lines.append(f"| Win Rate | {perf.win_rate:.2%} |")
        lines.append(f"| Profit Factor | {perf.profit_factor:.2f} |")
        lines.append(f"| Expectancy | {perf.expectancy:.4f} |")
        lines.append(f"| Avg Holding Period | {perf.avg_holding_period_days:.1f} days |")
        lines.append(f"| Total Trades | {perf.total_trades} |")
        lines.append(f"| Avg Trade Size | ${perf.avg_trade_size:,.2f} |")
        lines.append(f"| Portfolio Turnover | {perf.portfolio_turnover:.2f}x |")
        lines.append(f"| Total Fees | ${perf.total_fees_paid:,.2f} |")

    def _append_risk_table(self, lines: list[str], risk: Any) -> None:
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| VaR 95% | {risk.var_95:.4f} |")
        lines.append(f"| VaR 99% | {risk.var_99:.4f} |")
        lines.append(f"| CVaR 95% | {risk.cvar_95:.4f} |")
        lines.append(f"| CVaR 99% | {risk.cvar_99:.4f} |")
        lines.append(f"| Skewness | {risk.skewness:.3f} |")
        lines.append(f"| Kurtosis | {risk.kurtosis:.3f} |")
        lines.append(f"| Worst Day | {risk.worst_day:.2%} |")
        lines.append(f"| Worst Month | {risk.worst_month:.2%} |")
        lines.append(f"| Max Consecutive Losses | {risk.max_consecutive_losses} |")
        lines.append(f"| Max Consecutive Wins | {risk.max_consecutive_wins} |")
        if risk.beta is not None:
            lines.append(f"| Beta | {risk.beta:.3f} |")
        if risk.correlation is not None:
            lines.append(f"| Correlation | {risk.correlation:.3f} |")

    def _append_benchmark(self, lines: list[str], bench: BenchmarkResult) -> None:
        lines.append("| Metric | Strategy | Benchmark | Difference |")
        lines.append("|--------|----------|-----------|------------|")
        lines.append(
            f"| Total Return | {bench.strategy_return:.2%} | "
            f"{bench.benchmark_return:.2%} | "
            f"{bench.excess_return:.2%} |"
        )
        lines.append(
            f"| CAGR | {bench.strategy_cagr:.2%} | "
            f"{bench.benchmark_cagr:.2%} | "
            f"{bench.excess_cagr:.2%} |"
        )
        lines.append(
            f"| Sharpe | {bench.strategy_sharpe:.3f} | "
            f"{bench.benchmark_sharpe:.3f} | - |"
        )
        lines.append(
            f"| Max Drawdown | {bench.strategy_max_drawdown:.2%} | "
            f"{bench.benchmark_max_drawdown:.2%} | - |"
        )
        if bench.tracking_error is not None:
            lines.append(f"| Tracking Error | {bench.tracking_error:.4f} | - | - |")
        if bench.information_ratio is not None:
            lines.append(f"| Information Ratio | {bench.information_ratio:.3f} | - | - |")
        if bench.beta is not None:
            lines.append(f"| Beta | {bench.beta:.3f} | - | - |")
        if bench.correlation is not None:
            lines.append(f"| Correlation | {bench.correlation:.3f} | - | - |")

    def _append_walk_forward(self, lines: list[str], wf: WalkForwardResult) -> None:
        lines.append(f"**Windows Analyzed:** {len(wf.windows)}")
        lines.append(f"**Consistency Score:** {wf.consistency_score:.3f}")
        lines.append("")

        lines.append("### Aggregate In-Sample")
        self._append_performance_table(lines, wf.aggregate_in_sample)
        lines.append("")

        lines.append("### Aggregate Out-of-Sample")
        self._append_performance_table(lines, wf.aggregate_out_of_sample)
        lines.append("")

        lines.append("### Parameter Stability")
        for param, stability in wf.parameter_stability.items():
            lines.append(f"- {param}: {stability:.3f}")

    def _append_oos(self, lines: list[str], oos: OOSValidationResult) -> None:
        lines.append(f"**Valid:** {'✅ Yes' if oos.is_valid else '❌ No'}")
        lines.append(f"**Train End:** {oos.train_end}")
        lines.append(f"**Test Start:** {oos.test_start}")
        lines.append(f"**Overlap Detected:** {'Yes' if oos.overlap_detected else 'No'}")
        lines.append(f"**Look-Ahead Detected:** {'Yes' if oos.look_ahead_detected else 'No'}")

        if oos.violations:
            lines.append("")
            lines.append("### Violations")
            for v in oos.violations:
                lines.append(f"- {v}")

    def _append_sensitivity(self, lines: list[str], sens: list[SensitivityResult]) -> None:
        for s in sens:
            lines.append(f"### {s.parameter_name}")
            lines.append("")
            lines.append("| Value | Metric |")
            lines.append("|-------|--------|")
            for v, m in zip(s.parameter_values, s.metric_values):
                lines.append(f"| {v} | {m:.4f} |")
            lines.append("")
            lines.append(f"**Best:** {s.best_value} | **Worst:** {s.worst_value} | **Median:** {s.median_value:.4f} | **Stability:** {s.stability_score:.3f}")
            lines.append("")

    def _append_robustness(self, lines: list[str], rob: RobustnessResult) -> None:
        lines.append(f"**Baseline Sharpe:** {rob.baseline_performance.sharpe_ratio:.3f}")
        lines.append(f"**Worst Case Drawdown:** {rob.worst_case_drawdown:.2%}")
        lines.append(f"**Worst Case Return:** {rob.worst_case_return:.2%}")
        lines.append(f"**Degradation Threshold Exceeded:** {'Yes' if rob.degradation_threshold_exceeded else 'No'}")
        lines.append("")

        lines.append("### Top Stress Scenarios")
        lines.append("")
        lines.append("| Scenario | Return | Max DD | Sharpe |")
        lines.append("|----------|--------|--------|--------|")
        for scenario, perf in rob.scenarios[:10]:
            lines.append(f"| {scenario.name[:40]} | {perf.total_return:.2%} | {perf.max_drawdown:.2%} | {perf.sharpe_ratio:.3f} |")

    def _append_regime(self, lines: list[str], regime: dict[str, PerformanceSnapshot]) -> None:
        lines.append("| Regime | Return | Sharpe | Max DD | Trades |")
        lines.append("|--------|--------|--------|--------|--------|")
        for name, perf in regime.items():
            lines.append(f"| {name} | {perf.total_return:.2%} | {perf.sharpe_ratio:.3f} | {perf.max_drawdown:.2%} | {perf.total_trades} |")

    def _append_monte_carlo(self, lines: list[str], mc: MonteCarloResult) -> None:
        lines.append(f"**Iterations:** {mc.iterations:,}")
        lines.append(f"**Seed:** {mc.seed}")
        lines.append("")
        lines.append("### Return Distribution")
        lines.append("")
        lines.append(f"- **Median:** {mc.median_return:.2%}")
        lines.append(f"- **5th Percentile:** {mc.percentile_5:.2%}")
        lines.append(f"- **25th Percentile:** {mc.percentile_25:.2%}")
        lines.append(f"- **75th Percentile:** {mc.percentile_75:.2%}")
        lines.append(f"- **95th Percentile:** {mc.percentile_95:.2%}")
        lines.append(f"- **Worst Case:** {mc.worst_case_return:.2%}")
        lines.append(f"- **Best Case:** {mc.best_case_return:.2%}")
        lines.append(f"- **P(Loss):** {mc.probability_of_loss:.2%}")
        lines.append("")

        if mc.probability_of_drawdown_exceeding:
            lines.append("### Drawdown Exceedance Probability")
            for thresh, prob in mc.probability_of_drawdown_exceeding.items():
                lines.append(f"- P(DD > {thresh:.0%}) = {prob:.2%}")

    def _append_statistical(self, lines: list[str], stat: StatisticalValidationResult) -> None:
        lines.append(f"**Trade Count:** {stat.trade_count}")
        lines.append(f"**Sufficient Sample:** {'Yes' if stat.sufficient_sample else 'No'}")
        lines.append(f"**Statistically Significant:** {'Yes' if stat.is_statistically_significant else 'No'}")
        lines.append("")

        if stat.sharpe_confidence_interval:
            lines.append(
                f"**Sharpe CI (95%):** [{stat.sharpe_confidence_interval[0]:.3f}, "
                f"{stat.sharpe_confidence_interval[1]:.3f}]"
            )
        if stat.return_confidence_interval:
            lines.append(
                f"**Return CI (95%):** [{stat.return_confidence_interval[0]:.6f}, "
                f"{stat.return_confidence_interval[1]:.6f}]"
            )
        if stat.max_drawdown_confidence_interval:
            lines.append(
                f"**Max DD CI (95%):** [{stat.max_drawdown_confidence_interval[0]:.3f}, "
                f"{stat.max_drawdown_confidence_interval[1]:.3f}]"
            )

        if stat.warnings:
            lines.append("")
            lines.append("### Warnings")
            for w in stat.warnings:
                lines.append(f"- {w}")

    def _append_scoring(self, lines: list[str], score: StrategyScore) -> None:
        lines.append(f"**Total Score:** {score.total_score:.1f}/100")
        lines.append("")
        lines.append("| Component | Score | Weight |")
        lines.append("|-----------|-------|--------|")
        weights = {
            "return": 0.20,
            "risk": 0.20,
            "consistency": 0.15,
            "robustness": 0.15,
            "oos": 0.15,
            "statistical": 0.10,
            "benchmark": 0.05,
        }
        for comp, val in score.breakdown.items():
            lines.append(f"| {comp.capitalize()} | {val:.1f} | {weights.get(comp, 0):.0%} |")