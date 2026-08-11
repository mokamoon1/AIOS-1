"""Parameter Sensitivity Analysis (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from itertools import product
from typing import Any

import numpy as np

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    PerformanceSnapshot,
    SensitivityResult,
)
from aios.backtest.orchestrator import BacktestOrchestrator
from aios.config import load_settings
from aios.data.services import DataService


class SensitivityAnalyzer:
    """Analyzes parameter sensitivity of a strategy."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._sens_settings = self._settings.sensitivity

    def analyze(
        self,
        base_config: BacktestConfig,
        data_service: DataService,
        parameter_ranges: dict[str, list[float]] | None = None,
    ) -> list[SensitivityResult]:
        """Run parameter sensitivity analysis."""
        ranges = parameter_ranges or self._sens_settings.parameter_ranges
        if not ranges:
            return []

        # Generate all combinations
        param_names = list(ranges.keys())
        param_values = list(ranges.values())

        # Limit combinations
        all_combos = list(product(*param_values))
        max_combos = self._sens_settings.max_combinations
        if len(all_combos) > max_combos:
            # Sample evenly
            indices = np.linspace(0, len(all_combos) - 1, max_combos, dtype=int)
            all_combos = [all_combos[i] for i in indices]

        results: list[SensitivityResult] = []

        for combo in all_combos:
            params = dict(zip(param_names, combo))
            config = self._apply_parameters(base_config, params)

            # Run backtest
            result = self._run_backtest(config, data_service)

            # Extract metric for this parameter set
            metric_value = self._extract_metric(result)

            # Store individual parameter results
            for name, value in params.items():
                # This is a simplified approach - in practice you'd want
                # to track each parameter independently
                pass

        # Build sensitivity results per parameter
        return self._build_sensitivity_results(param_names, all_combos, base_config, data_service)

    def _build_sensitivity_results(
        self,
        param_names: list[str],
        all_combos: list[tuple[float, ...]],
        base_config: BacktestConfig,
        data_service: DataService,
    ) -> list[SensitivityResult]:
        """Build sensitivity results for each parameter."""
        results = []

        for i, param_name in enumerate(param_names):
            # Group by this parameter's value
            param_to_metric: dict[float, list[float]] = {}
            for combo in all_combos:
                param_val = combo[i]
                config = self._apply_parameters(base_config, dict(zip(param_names, combo)))
                result = self._run_backtest(config, data_service)
                metric = self._extract_metric(result)
                param_to_metric.setdefault(param_val, []).append(metric)

            # Aggregate metrics per parameter value
            values = sorted(param_to_metric.keys())
            metric_means = [float(np.mean(param_to_metric[v])) for v in values]

            if metric_means:
                best_idx = np.argmax(metric_means)
                worst_idx = np.argmin(metric_means)

                # Stability score: 1 - coefficient of variation
                if len(metric_means) > 1 and np.mean(metric_means) != 0:
                    cv = np.std(metric_means) / abs(np.mean(metric_means))
                    stability = max(0.0, 1.0 - min(cv, 1.0))
                else:
                    stability = 1.0

                results.append(
                    SensitivityResult(
                        parameter_name=param_name,
                        parameter_values=values,
                        metric_values=metric_means,
                        best_value=values[best_idx],
                        worst_value=values[worst_idx],
                        median_value=float(np.median(metric_means)),
                        stability_score=stability,
                    )
                )

        return results

    def _apply_parameters(
        self, config: BacktestConfig, params: dict[str, float]
    ) -> BacktestConfig:
        """Apply parameters to create a new config."""
        # Create a new config with modified parameters
        # This modifies engine_config or other settings
        engine_config = dict(config.engine_config)
        engine_config.update(params)

        return BacktestConfig(
            start_date=config.start_date,
            end_date=config.end_date,
            timeframe=config.timeframe,
            universe=config.universe,
            initial_cash=config.initial_cash,
            currency=config.currency,
            transaction_costs=config.transaction_costs,
            max_position_pct=config.max_position_pct,
            max_sector_pct=config.max_sector_pct,
            max_position_weight=config.max_position_weight,
            max_portfolio_exposure=config.max_portfolio_exposure,
            max_sector_exposure=config.max_sector_exposure,
            confidence_scaling=config.confidence_scaling,
            risk_score_scaling=config.risk_score_scaling,
            rebalance_threshold=config.rebalance_threshold,
            min_trade_size=config.min_trade_size,
            engine_config=engine_config,
        )

    def _run_backtest(
        self, config: BacktestConfig, data_service: DataService
    ) -> BacktestResult:
        """Run a single backtest."""
        import asyncio

        async def _run():
            orch = BacktestOrchestrator(config, data_service)
            return await orch.run()

        return asyncio.run(_run())

    def _extract_metric(self, result: BacktestResult) -> float:
        """Extract the optimization metric from result."""
        metric_name = self._sens_settings.optimization_metric
        perf = result.performance

        metric_map = {
            "sharpe_ratio": perf.sharpe_ratio,
            "sortino_ratio": perf.sortino_ratio,
            "calmar_ratio": perf.calmar_ratio,
            "total_return": perf.total_return,
            "cagr": perf.cagr,
            "max_drawdown": -perf.max_drawdown,  # Negative because lower is better
            "profit_factor": perf.profit_factor,
            "expectancy": perf.expectancy,
        }

        return metric_map.get(metric_name, perf.sharpe_ratio)