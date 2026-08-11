"""Statistical Validation (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import scipy.stats as stats

from aios.backtest.models import (
    BacktestResult,
    PerformanceSnapshot,
    StatisticalValidationResult,
)
from aios.config import load_settings


class StatisticalValidator:
    """Validates statistical significance of backtest results."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._stat_settings = self._settings.statistical_validation

    def validate(self, result: BacktestResult) -> StatisticalValidationResult:
        """Run statistical validation on backtest result."""
        warnings: list[str] = []

        # Extract daily returns from equity curve
        daily_returns = self._extract_daily_returns(result)
        trade_pnls = self._extract_trade_pnls(result)

        # Check sample sizes
        n_days = len(daily_returns)
        n_trades = len(trade_pnls)

        sufficient_sample = (
            n_days >= self._stat_settings.min_trades_for_sharpe
            and n_trades >= self._stat_settings.min_trades_for_drawdown
        )

        if not sufficient_sample:
            warnings.append(
                f"Insufficient sample: {n_days} days, {n_trades} trades"
            )

        # Sharpe ratio confidence interval
        sharpe_ci = self._sharpe_confidence_interval(daily_returns)
        if sharpe_ci is None:
            warnings.append("Cannot compute Sharpe CI: insufficient data or zero variance")

        # Return confidence interval
        return_ci = self._mean_confidence_interval(daily_returns)

        # Max drawdown confidence interval
        dd_ci = self._drawdown_confidence_interval(result.equity_curve)

        # Statistical significance
        is_significant = self._test_significance(daily_returns)

        # Stability checks
        if sharpe_ci:
            sharpe_width = sharpe_ci[1] - sharpe_ci[0]
            if sharpe_width > self._stat_settings.sharpe_stability_threshold * 2:
                warnings.append(f"Sharpe ratio unstable: CI width = {sharpe_width:.3f}")

        return StatisticalValidationResult(
            sharpe_confidence_interval=sharpe_ci,
            return_confidence_interval=return_ci,
            max_drawdown_confidence_interval=dd_ci,
            trade_count=n_trades,
            is_statistically_significant=is_significant and sufficient_sample,
            warnings=warnings,
            sufficient_sample=sufficient_sample,
        )

    def _extract_daily_returns(self, result: BacktestResult) -> np.ndarray:
        """Extract daily returns from equity curve."""
        if len(result.equity_curve) < 2:
            return np.array([])

        returns = []
        for i in range(1, len(result.equity_curve)):
            prev_eq = result.equity_curve[i - 1].equity
            curr_eq = result.equity_curve[i].equity
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)
        return np.array(returns)

    def _extract_trade_pnls(self, result: BacktestResult) -> np.ndarray:
        """Extract trade P&Ls from fills."""
        pnls = []
        trades_by_order = {}
        for fill in result.fills:
            oid = getattr(fill, "order_id", None)
            if oid:
                trades_by_order.setdefault(oid, []).append(fill)

        for order_fills in trades_by_order.values():
            buy_fills = [f for f in order_fills if getattr(f, "side", None) == "buy"]
            sell_fills = [f for f in order_fills if getattr(f, "side", None) == "sell"]
            if buy_fills and sell_fills:
                entry = buy_fills[0]
                exit = sell_fills[0]
                pnl = getattr(exit, "realized_pnl", 0.0)
                pnls.append(pnl)
        return np.array(pnls)

    def _sharpe_confidence_interval(
        self, returns: np.ndarray
    ) -> tuple[float, float] | None:
        """Compute confidence interval for Sharpe ratio using bootstrap."""
        if len(returns) < 10 or np.std(returns) == 0:
            return None

        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
        n = len(returns)
        # Standard error of Sharpe (approximate)
        se = np.sqrt((1 + 0.5 * sharpe**2) / n)
        z = stats.norm.ppf((1 + self._stat_settings.confidence_level) / 2)
        margin = z * se

        return (sharpe - margin, sharpe + margin)

    def _mean_confidence_interval(
        self, returns: np.ndarray
    ) -> tuple[float, float] | None:
        """Compute confidence interval for mean return."""
        if len(returns) < 2:
            return None

        mean = np.mean(returns)
        se = stats.sem(returns)
        z = stats.norm.ppf((1 + self._stat_settings.confidence_level) / 2)
        margin = z * se

        return (mean - margin, mean + margin)

    def _drawdown_confidence_interval(
        self, equity_curve: list
    ) -> tuple[float, float] | None:
        """Compute confidence interval for max drawdown using bootstrap."""
        if len(equity_curve) < 10:
            return None

        equity = np.array([ep.equity for ep in equity_curve])
        returns = np.diff(equity) / equity[:-1]

        # Bootstrap drawdowns
        n_bootstrap = 1000
        drawdowns = []

        for _ in range(n_bootstrap):
            sample = np.random.choice(returns, size=len(returns), replace=True)
            eq = np.cumprod(1 + sample)
            eq = np.concatenate([[1.0], eq])
            dd = self._max_drawdown(eq)
            drawdowns.append(dd)

        drawdowns = np.array(drawdowns)
        alpha = (1 - self._stat_settings.confidence_level) / 2
        lower = np.percentile(drawdowns, alpha * 100)
        upper = np.percentile(drawdowns, (1 - alpha) * 100)

        return (float(lower), float(upper))

    def _max_drawdown(self, equity: np.ndarray) -> float:
        peak = equity[0]
        max_dd = 0.0
        for v in equity:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _test_significance(self, returns: np.ndarray) -> bool:
        """Test if mean return is significantly different from zero."""
        if len(returns) < 10:
            return False

        # One-sample t-test
        t_stat, p_value = stats.ttest_1samp(returns, 0.0)
        alpha = 1 - self._stat_settings.confidence_level
        return p_value < alpha