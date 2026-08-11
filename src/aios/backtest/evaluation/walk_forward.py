"""Walk-Forward Analysis (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    PerformanceSnapshot,
    WalkForwardMode,
    WalkForwardResult,
    WalkForwardWindow,
)
from aios.backtest.orchestrator import BacktestOrchestrator
from aios.config import load_settings
from aios.data.services import DataService


class WalkForwardAnalyzer:
    """Performs walk-forward analysis on a strategy."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._wf_settings = self._settings.walk_forward

    def analyze(
        self,
        config: BacktestConfig,
        data_service: DataService,
        parameter_grid: dict[str, list[float]] | None = None,
    ) -> WalkForwardResult:
        """Run walk-forward analysis."""
        windows = self._generate_windows(config)
        if not windows:
            raise ValueError("Insufficient data for walk-forward windows")

        window_results: list[WalkForwardWindow] = []

        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            # Create training config
            train_config = self._create_window_config(
                config, train_start, train_end
            )

            # Run backtest on training window (for parameter optimization if enabled)
            train_params = self._optimize_parameters(
                train_config, data_service, parameter_grid
            )

            # Create test config with optimized parameters
            test_config = self._create_window_config(
                config, test_start, test_end
            )
            self._apply_parameters(test_config, train_params)

            # Run backtest on test window
            train_result = self._run_backtest(train_config, data_service)
            test_result = self._run_backtest(test_config, data_service)

            window_results.append(
                WalkForwardWindow(
                    window_index=i,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    in_sample_performance=train_result.performance,
                    out_of_sample_performance=test_result.performance,
                    parameters=train_params,
                )
            )

        # Aggregate results
        agg_is = self._aggregate_performance([w.in_sample_performance for w in window_results])
        agg_oos = self._aggregate_performance([w.out_of_sample_performance for w in window_results])

        consistency = self._compute_consistency(window_results)
        param_stability = self._compute_parameter_stability(window_results)

        return WalkForwardResult(
            windows=window_results,
            aggregate_in_sample=agg_is,
            aggregate_out_of_sample=agg_oos,
            consistency_score=consistency,
            parameter_stability=param_stability,
        )

    def _generate_windows(
        self, config: BacktestConfig
    ) -> list[tuple[date, date, date, date]]:
        """Generate walk-forward windows."""
        start = config.start_date
        end = config.end_date
        train_days = self._wf_settings.train_window_days
        test_days = self._wf_settings.test_window_days
        step_days = self._wf_settings.step_days

        total_days = (end - start).days
        windows = []

        if self._wf_settings.mode == "expanding":
            # Expanding window: training grows, test moves forward
            train_start = start
            test_start = start + timedelta(days=train_days)

            while test_start + timedelta(days=test_days) <= end:
                train_end = test_start - timedelta(days=1)
                test_end = min(test_start + timedelta(days=test_days) - timedelta(days=1), end)

                if (train_end - train_start).days >= self._wf_settings.min_train_observations:
                    windows.append((train_start, train_end, test_start, test_end))

                test_start += timedelta(days=step_days)
        else:
            # Rolling window: fixed-size training window
            train_start = start
            train_end = start + timedelta(days=train_days - 1)
            test_start = train_end + timedelta(days=1)

            while test_start + timedelta(days=test_days - 1) <= end:
                test_end = min(test_start + timedelta(days=test_days - 1), end)

                if (train_end - train_start).days >= self._wf_settings.min_train_observations:
                    windows.append((train_start, train_end, test_start, test_end))

                train_start += timedelta(days=step_days)
                train_end += timedelta(days=step_days)
                test_start += timedelta(days=step_days)

        return windows

    def _create_window_config(
        self, base: BacktestConfig, start: date, end: date
    ) -> BacktestConfig:
        """Create a backtest config for a specific window."""
        return BacktestConfig(
            start_date=start,
            end_date=end,
            timeframe=base.timeframe,
            universe=base.universe,
            initial_cash=base.initial_cash,
            currency=base.currency,
            transaction_costs=base.transaction_costs,
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

    def _optimize_parameters(
        self,
        config: BacktestConfig,
        data_service: DataService,
        parameter_grid: dict[str, list[float]] | None,
    ) -> dict[str, float]:
        """Optimize parameters on training window (placeholder)."""
        # If no grid or optimization disabled, return empty dict
        if not self._wf_settings.optimize_parameters or not parameter_grid:
            return {}

        # Placeholder: In a real implementation, this would run multiple
        # backtests with different parameter combinations and select the best
        # based on the optimization metric.
        return {}

    def _apply_parameters(
        self, config: BacktestConfig, params: dict[str, float]
    ) -> None:
        """Apply optimized parameters to config (placeholder)."""
        # In a real implementation, this would modify the config's
        # engine_config or other settings based on the optimized parameters.
        pass

    def _run_backtest(
        self, config: BacktestConfig, data_service: DataService
    ) -> BacktestResult:
        """Run a single backtest (placeholder)."""
        # This would use the actual BacktestOrchestrator
        # For now, return a minimal result
        import asyncio

        async def _run():
            orch = BacktestOrchestrator(config, data_service)
            return await orch.run()

        return asyncio.run(_run())

    def _aggregate_performance(
        self, performances: Sequence[PerformanceSnapshot]
    ) -> PerformanceSnapshot:
        """Aggregate multiple performance snapshots."""
        if not performances:
            return PerformanceSnapshot(
                total_return=0.0,
                annualized_return=0.0,
                cagr=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                max_drawdown=0.0,
                avg_drawdown=0.0,
                max_drawdown_duration_days=0,
                recovery_time_days=0,
                win_rate=0.0,
                loss_rate=0.0,
                profit_factor=0.0,
                expectancy=0.0,
                avg_holding_period_days=0.0,
                avg_exposure=0.0,
                max_exposure=0.0,
                avg_position_concentration=0.0,
                max_position_concentration=0.0,
                avg_sector_concentration=0.0,
                max_sector_concentration=0.0,
                portfolio_turnover=0.0,
                avg_trade_size=0.0,
                total_trades=0,
                total_fees_paid=0.0,
            )

        # Simple average for most metrics
        return PerformanceSnapshot(
            total_return=float(np.mean([p.total_return for p in performances])),
            annualized_return=float(np.mean([p.annualized_return for p in performances])),
            cagr=float(np.mean([p.cagr for p in performances])),
            sharpe_ratio=float(np.mean([p.sharpe_ratio for p in performances])),
            sortino_ratio=float(np.mean([p.sortino_ratio for p in performances])),
            calmar_ratio=float(np.mean([p.calmar_ratio for p in performances])),
            max_drawdown=float(np.max([p.max_drawdown for p in performances])),
            avg_drawdown=float(np.mean([p.avg_drawdown for p in performances])),
            max_drawdown_duration_days=int(
                np.max([p.max_drawdown_duration_days for p in performances])
            ),
            recovery_time_days=int(
                np.mean([p.recovery_time_days for p in performances])
            ),
            win_rate=float(np.mean([p.win_rate for p in performances])),
            loss_rate=float(np.mean([p.loss_rate for p in performances])),
            profit_factor=float(np.mean([p.profit_factor for p in performances])),
            expectancy=float(np.mean([p.expectancy for p in performances])),
            avg_holding_period_days=float(
                np.mean([p.avg_holding_period_days for p in performances])
            ),
            avg_exposure=float(np.mean([p.avg_exposure for p in performances])),
            max_exposure=float(np.max([p.max_exposure for p in performances])),
            avg_position_concentration=float(
                np.mean([p.avg_position_concentration for p in performances])
            ),
            max_position_concentration=float(
                np.max([p.max_position_concentration for p in performances])
            ),
            avg_sector_concentration=float(
                np.mean([p.avg_sector_concentration for p in performances])
            ),
            max_sector_concentration=float(
                np.max([p.max_sector_concentration for p in performances])
            ),
            portfolio_turnover=float(np.mean([p.portfolio_turnover for p in performances])),
            avg_trade_size=float(np.mean([p.avg_trade_size for p in performances])),
            total_trades=int(np.sum([p.total_trades for p in performances])),
            total_fees_paid=float(np.sum([p.total_fees_paid for p in performances])),
        )

    def _compute_consistency(self, windows: Sequence[WalkForwardWindow]) -> float:
        """Compute consistency between in-sample and out-of-sample performance."""
        if not windows:
            return 0.0

        is_sharpes = [w.in_sample_performance.sharpe_ratio for w in windows]
        oos_sharpes = [w.out_of_sample_performance.sharpe_ratio for w in windows]

        # Correlation between IS and OOS Sharpe ratios
        if len(is_sharpes) < 2:
            return 0.0

        corr = np.corrcoef(is_sharpes, oos_sharpes)[0, 1]
        return float(max(0.0, corr))

    def _compute_parameter_stability(
        self, windows: Sequence[WalkForwardWindow]
    ) -> dict[str, float]:
        """Compute stability of parameters across windows."""
        if not windows:
            return {}

        all_params = {}
        for w in windows:
            for k, v in w.parameters.items():
                all_params.setdefault(k, []).append(v)

        stability = {}
        for k, values in all_params.items():
            if len(values) > 1:
                cv = np.std(values) / (np.mean(values) if np.mean(values) != 0 else 1.0)
                stability[k] = float(max(0.0, 1.0 - min(cv, 1.0)))
            else:
                stability[k] = 1.0

        return stability