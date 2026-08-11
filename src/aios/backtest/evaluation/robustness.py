"""Robustness Analysis (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    PerformanceSnapshot,
    RobustnessResult,
    RobustnessScenario,
)
from aios.backtest.orchestrator import BacktestOrchestrator
from aios.config import load_settings
from aios.data.services import DataService


class RobustnessAnalyzer:
    """Tests strategy robustness under various stress scenarios."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._rob_settings = self._settings.robustness

    def analyze(
        self,
        base_config: BacktestConfig,
        data_service: DataService,
        baseline_result: BacktestResult | None = None,
    ) -> RobustnessResult:
        """Run robustness analysis across stress scenarios."""
        # Get baseline if not provided
        if baseline_result is None:
            baseline_result = self._run_backtest(base_config, data_service)

        baseline_perf = baseline_result.performance

        # Generate all scenarios
        scenarios = self._generate_scenarios()

        scenario_results: list[tuple[RobustnessScenario, PerformanceSnapshot]] = []

        for scenario in scenarios:
            config = self._apply_scenario(base_config, scenario)
            result = self._run_backtest(config, data_service)
            scenario_results.append((scenario, result.performance))

        # Find worst case
        worst_dd = max(
            (perf.max_drawdown for _, perf in scenario_results),
            default=baseline_perf.max_drawdown,
        )
        worst_return = min(
            (perf.total_return for _, perf in scenario_results),
            default=baseline_perf.total_return,
        )

        # Check degradation thresholds
        return_degradation = (
            (baseline_perf.total_return - worst_return)
            / abs(baseline_perf.total_return)
            if baseline_perf.total_return != 0
            else 0.0
        )
        dd_increase = (
            (worst_dd - baseline_perf.max_drawdown)
            / baseline_perf.max_drawdown
            if baseline_perf.max_drawdown != 0
            else 0.0
        )

        degradation_exceeded = (
            return_degradation > self._rob_settings.max_return_degradation
            or dd_increase > self._rob_settings.max_drawdown_increase
        )

        return RobustnessResult(
            baseline_performance=baseline_perf,
            scenarios=scenario_results,
            worst_case_drawdown=worst_dd,
            worst_case_return=worst_return,
            degradation_threshold_exceeded=degradation_exceeded,
        )

    def _generate_scenarios(self) -> list[RobustnessScenario]:
        """Generate all stress scenarios."""
        scenarios = []

        for comm_mult in self._rob_settings.commission_multipliers:
            for spread_mult in self._rob_settings.spread_multipliers:
                for slip_mult in self._rob_settings.slippage_multipliers:
                    for delay in self._rob_settings.execution_delays:
                        for min_fill in self._rob_settings.min_fill_fractions:
                            name = (
                                f"comm={comm_mult}x_spread={spread_mult}x_"
                                f"slip={slip_mult}x_delay={delay}_fill={min_fill}"
                            )
                            scenarios.append(
                                RobustnessScenario(
                                    name=name,
                                    commission_multiplier=comm_mult,
                                    spread_multiplier=spread_mult,
                                    slippage_multiplier=slip_mult,
                                    execution_delay_bars=delay,
                                    min_fill_fraction=min_fill,
                                )
                            )

        return scenarios

    def _apply_scenario(
        self, base: BacktestConfig, scenario: RobustnessScenario
    ) -> BacktestConfig:
        """Apply a stress scenario to the config."""
        tc = base.transaction_costs

        new_tc = tc.model_copy(
            update={
                "commission_bps": tc.commission_bps * scenario.commission_multiplier,
                "spread_bps": tc.spread_bps * scenario.spread_multiplier,
                "slippage_bps": tc.slippage_bps * scenario.slippage_multiplier,
                "min_fill_fraction": scenario.min_fill_fraction
                or tc.min_fill_fraction,
            }
        )

        return BacktestConfig(
            start_date=base.start_date,
            end_date=base.end_date,
            timeframe=base.timeframe,
            universe=base.universe,
            initial_cash=base.initial_cash,
            currency=base.currency,
            transaction_costs=new_tc,
            max_position_pct=base.max_position_pct,
            max_sector_pct=base.max_sector_pct,
            max_position_weight=base.max_position_weight,
            max_portfolio_exposure=base.max_portfolio_exposure,
            max_sector_exposure=base.max_sector_exposure,
            confidence_scaling=base.confidence_scaling,
            risk_score_scaling=base.risk_score_scaling,
            rebalance_threshold=base.rebalance_threshold,
            min_trade_size=base.min_trade_size,
            engine_config=base.engine_config,
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