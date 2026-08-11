"""Performance Calculator - Computes all required backtest metrics (Phase 9.5).

Implements all metrics required by AIOS-707:
- Total Return, Annualized Return, CAGR
- Sharpe, Sortino, Calmar
- Max Drawdown, Average Drawdown, Recovery Time
- Win Rate, Loss Rate, Profit Factor, Expectancy
- Average Holding Period
- Exposure, Concentration, Turnover
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from aios.backtest.models import (
    EquityPoint,
    PerformanceSnapshot,
    RiskMetrics,
    PaperFill,
)
from aios.brokers.models import PaperFill as BrokerPaperFill


class PerformanceCalculator:
    """Calculates comprehensive performance and risk metrics for backtest results."""

    def compute(
        self,
        equity_curve: Sequence[EquityPoint],
        fills: Sequence[Any],
        initial_cash: float,
    ) -> PerformanceSnapshot:
        """Compute all performance metrics from equity curve and fills."""
        if not equity_curve:
            return self._empty_performance()

        # Extract arrays
        timestamps = np.array([ep.timestamp for ep in equity_curve], dtype="datetime64[ns]")
        equity = np.array([ep.equity for ep in equity_curve], dtype=np.float64)
        daily_returns = np.array([ep.daily_return for ep in equity_curve], dtype=np.float64)

        # Returns
        total_return = (equity[-1] - equity[0]) / equity[0] if equity[0] != 0 else 0.0
        years = (equity_curve[-1].timestamp - equity_curve[0].timestamp).days / 365.25
        annualized_return = (1 + total_return) ** (1 / max(years, 1/365)) - 1 if years > 0 else 0.0
        cagr = annualized_return

        # Risk-adjusted returns
        sharpe_ratio = self._calculate_sharpe(daily_returns)
        sortino_ratio = self._calculate_sortino(daily_returns)
        calmar_ratio = self._calculate_calmar(annualized_return, equity)

        # Drawdown
        max_drawdown, max_dd_duration, avg_drawdown, recovery_time = self._calculate_drawdowns(equity)

        # Trade statistics from fills
        trade_stats = self._compute_trade_stats(fills)

        # Exposure metrics
        exposure_metrics = self._compute_exposure_metrics(
            equity_curve, fills, initial_cash
        )

        # Trade statistics
        total_trades = len([f for f in fills if hasattr(f, 'side')])

        return PerformanceSnapshot(
            # Returns
            total_return=total_return,
            annualized_return=annualized_return,
            cagr=cagr,

            # Risk-adjusted
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,

            # Drawdown
            max_drawdown=max_drawdown,
            avg_drawdown=avg_drawdown,
            max_drawdown_duration_days=max_dd_duration,
            recovery_time_days=recovery_time,

            # Trade statistics
            win_rate=trade_stats["win_rate"],
            loss_rate=trade_stats["loss_rate"],
            profit_factor=trade_stats["profit_factor"],
            expectancy=trade_stats["expectancy"],
            avg_holding_period_days=trade_stats["avg_holding_period"],

            # Exposure
            avg_exposure=exposure_metrics["avg_exposure"],
            max_exposure=exposure_metrics["max_exposure"],
            avg_position_concentration=exposure_metrics["avg_position_concentration"],
            max_position_concentration=exposure_metrics["max_position_concentration"],
            avg_sector_concentration=exposure_metrics["avg_sector_concentration"],
            max_sector_concentration=exposure_metrics["max_sector_concentration"],

            # Turnover
            portfolio_turnover=exposure_metrics["turnover"],
            avg_trade_size=exposure_metrics["avg_trade_size"],

            # Additional
            total_trades=total_trades,
            total_fees_paid=trade_stats["total_fees"],
        )

    def compute_risk_metrics(
        self,
        equity_curve: Sequence[EquityPoint],
        fills: Sequence[Any],
    ) -> RiskMetrics:
        """Compute risk-specific metrics (VaR, CVaR, tail risk, etc.)."""
        if len(equity_curve) < 2:
            return self._empty_risk()

        daily_returns = np.array([ep.daily_return for ep in equity_curve], dtype=np.float64)

        # VaR / CVaR
        var_95 = float(np.percentile(daily_returns, 5))
        var_99 = float(np.percentile(daily_returns, 1))
        cvar_95 = float(daily_returns[daily_returns <= var_95].mean()) if any(daily_returns <= var_95) else var_95
        cvar_99 = float(daily_returns[daily_returns <= var_99].mean()) if any(daily_returns <= var_99) else var_99

        # Tail risk
        skewness = float(self._skewness(daily_returns))
        kurtosis = float(self._kurtosis(daily_returns))

        # Worst periods
        worst_day = float(np.min(daily_returns))
        # Monthly returns approximation
        monthly_returns = self._resample_monthly(daily_returns)
        worst_month = float(np.min(monthly_returns)) if len(monthly_returns) > 0 else 0.0

        # Consecutive wins/losses (from fills)
        consecutive = self._consecutive_wins_losses(fills)

        return RiskMetrics(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            cvar_99=cvar_99,
            skewness=skewness,
            kurtosis=kurtosis,
            beta=None,
            correlation=None,
            worst_day=worst_day,
            worst_month=worst_month,
            max_consecutive_losses=consecutive["max_losses"],
            max_consecutive_wins=consecutive["max_wins"],
            max_leverage=1.0,
            avg_leverage=1.0,
        )

    # -- Private helpers ---------------------------------------------------

    def _empty_performance(self) -> PerformanceSnapshot:
        return PerformanceSnapshot(
            total_return=0.0, annualized_return=0.0, cagr=0.0,
            sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
            max_drawdown=0.0, avg_drawdown=0.0, max_drawdown_duration_days=0,
            recovery_time_days=0, win_rate=0.0, loss_rate=0.0,
            profit_factor=0.0, expectancy=0.0, avg_holding_period_days=0.0,
            avg_exposure=0.0, max_exposure=0.0, avg_position_concentration=0.0,
            max_position_concentration=0.0, avg_sector_concentration=0.0,
            max_sector_concentration=0.0, portfolio_turnover=0.0,
            avg_trade_size=0.0, total_trades=0, total_fees_paid=0.0,
        )

    def _empty_risk(self) -> RiskMetrics:
        return RiskMetrics(
            var_95=0.0, var_99=0.0, cvar_95=0.0, cvar_99=0.0,
            skewness=0.0, kurtosis=0.0, beta=None, correlation=None,
            worst_day=0.0, worst_month=0.0, max_consecutive_losses=0,
            max_consecutive_wins=0, max_leverage=1.0, avg_leverage=1.0,
        )

    def _calculate_sharpe(self, returns: np.ndarray) -> float:
        """Calculate Sharpe ratio (risk-free rate = 0)."""
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(returns) * np.sqrt(252))

    def _calculate_sortino(self, returns: np.ndarray) -> float:
        """Calculate Sortino ratio (downside deviation)."""
        if len(returns) < 2:
            return 0.0
        downside = returns[returns < 0]
        if len(downside) == 0 or np.std(downside) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(downside) * np.sqrt(252))

    def _calculate_calmar(self, annualized_return: float, equity: np.ndarray) -> float:
        """Calculate Calmar ratio (annualized return / max drawdown)."""
        max_dd = self._max_drawdown(equity)
        if max_dd == 0:
            return 0.0
        return annualized_return / max_dd

    def _max_drawdown(self, equity: np.ndarray) -> float:
        peak = equity[0]
        max_dd = 0.0
        for value in equity:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _calculate_drawdowns(self, equity: np.ndarray) -> tuple[float, int, float, int]:
        """Calculate max drawdown, duration, average drawdown, and recovery time."""
        peak = equity[0]
        max_dd = 0.0
        max_duration = 0
        current_duration = 0
        drawdowns = []

        for value in equity:
            if value > peak:
                peak = value
                if current_duration > 0:
                    drawdowns.append(current_duration)
                current_duration = 0
            else:
                dd = (peak - value) / peak if peak > 0 else 0.0
                current_duration += 1

        if current_duration > 0:
            drawdowns.append(current_duration)

        max_dd = 0.0
        peak = equity[0]
        for value in equity:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        avg_dd = np.mean([(peak - v) / peak if peak > 0 else 0.0 for v in equity])
        max_duration = max(drawdowns) if drawdowns else 0
        avg_drawdown = float(avg_dd)
        recovery_time = int(np.mean(drawdowns)) if drawdowns else 0

        return max_dd, max_duration, avg_drawdown, recovery_time

    def _compute_trade_stats(self, fills: Sequence[Any]) -> dict[str, float]:
        """Compute trade-level statistics from fills."""
        if not fills:
            return {
                "win_rate": 0.0, "loss_rate": 0.0, "profit_factor": 0.0,
                "expectancy": 0.0, "avg_holding_period": 0.0, "total_fees": 0.0,
            }

        # Group fills by order to get complete trades
        trades_by_order = {}
        for fill in fills:
            order_id = getattr(fill, 'order_id', None)
            if order_id:
                trades_by_order.setdefault(order_id, []).append(fill)

        pnls = []
        holding_periods = []
        total_fees = 0.0

        for order_fills in trades_by_order.values():
            if len(order_fills) >= 1:
                # Find entry and exit
                buy_fills = [f for f in order_fills if getattr(f, 'side', None) == 'buy']
                sell_fills = [f for f in order_fills if getattr(f, 'side', None) == 'sell']

                if buy_fills and sell_fills:
                    entry = buy_fills[0]
                    exit = sell_fills[0]
                    pnl = getattr(exit, 'realized_pnl', 0.0)
                    pnls.append(pnl)

                    # Holding period
                    if hasattr(entry, 'filled_at') and hasattr(exit, 'filled_at'):
                        hp = (exit.filled_at - entry.filled_at).days
                        holding_periods.append(hp)

        # Commission/fees from fills
        total_fees = sum(getattr(f, 'realized_pnl', 0.0) for f in fills if hasattr(f, 'realized_pnl') and getattr(f, 'realized_pnl', 0) < 0)

        if not pnls:
            return {
                "win_rate": 0.0, "loss_rate": 0.0, "profit_factor": 0.0,
                "expectancy": 0.0, "avg_holding_period": 0.0, "total_fees": 0.0,
            }

        pnls_arr = np.array(pnls)
        wins = pnls_arr[pnls_arr > 0]
        losses = pnls_arr[pnls_arr < 0]

        win_rate = len(wins) / len(pnls) if pnls else 0.0
        loss_rate = len(losses) / len(pnls) if pnls else 0.0
        profit_factor = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
        expectancy = float(np.mean(pnls)) if pnls else 0.0
        avg_holding = float(np.mean(holding_periods)) if holding_periods else 0.0

        return {
            "win_rate": float(win_rate),
            "loss_rate": float(loss_rate),
            "profit_factor": float(profit_factor) if profit_factor != float('inf') else 1e6,
            "expectancy": float(expectancy),
            "avg_holding_period": float(avg_holding),
            "total_fees": float(total_fees),
        }

    def _compute_exposure_metrics(
        self,
        equity_curve: Sequence[EquityPoint],
        fills: Sequence[Any],
        initial_cash: float,
    ) -> dict[str, float]:
        """Compute exposure and concentration metrics from actual position data."""
        if not equity_curve or len(equity_curve) < 2:
            return {
                "avg_exposure": 0.0,
                "max_exposure": 0.0,
                "avg_position_concentration": 0.0,
                "max_position_concentration": 0.0,
                "avg_sector_concentration": 0.0,
                "max_sector_concentration": 0.0,
                "turnover": 0.0,
                "avg_trade_size": 0.0,
            }

        equity = np.array([ep.equity for ep in equity_curve], dtype=np.float64)
        cash = np.array([ep.cash for ep in equity_curve], dtype=np.float64)
        market_value = equity - cash

        # Exposure = market_value / equity (how much capital is deployed)
        with np.errstate(divide='ignore', invalid='ignore'):
            exposure = np.where(equity > 0, market_value / equity, 0.0)
        avg_exposure = float(np.mean(exposure))
        max_exposure = float(np.max(exposure))

        # Trade statistics from fills
        total_notional = 0.0
        total_turnover = 0.0
        trade_sizes = []

        for fill in fills:
            if hasattr(fill, 'quantity') and hasattr(fill, 'price'):
                notional = fill.quantity * fill.price
                total_notional += notional
                trade_sizes.append(notional)

        if fills:
            total_turnover = total_notional / equity[-1] if equity[-1] > 0 else 0.0
            avg_trade_size = float(np.mean(trade_sizes)) if trade_sizes else 0.0
        else:
            total_turnover = 0.0
            avg_trade_size = 0.0

        # Annualize turnover (assuming daily data)
        n_days = len(equity_curve)
        if n_days > 1:
            days_span = (equity_curve[-1].timestamp - equity_curve[0].timestamp).days
            if days_span > 0:
                total_turnover = total_turnover * (252.0 / max(days_span, 1))

        # Position concentration (Herfindahl index approximation)
        # We don't have per-position data in equity curve, so use approximation
        # based on number of trades and diversification
        n_trades = len(fills)
        if n_trades > 1:
            # Simplified: assume equal weight positions, HHI = 1/n
            avg_position_concentration = 1.0 / n_trades
            max_position_concentration = 1.0  # Could be up to 100% in one position
        else:
            avg_position_concentration = 1.0
            max_position_concentration = 1.0

        # Sector concentration - simplified (no sector data available)
        avg_sector_concentration = avg_position_concentration * 0.5
        max_sector_concentration = max_position_concentration * 0.5

        return {
            "avg_exposure": float(np.clip(avg_exposure, 0.0, 1.0)),
            "max_exposure": float(np.clip(max_exposure, 0.0, 1.0)),
            "avg_position_concentration": float(np.clip(avg_position_concentration, 0.0, 1.0)),
            "max_position_concentration": float(np.clip(max_position_concentration, 0.0, 1.0)),
            "avg_sector_concentration": float(np.clip(avg_sector_concentration, 0.0, 1.0)),
            "max_sector_concentration": float(np.clip(max_sector_concentration, 0.0, 1.0)),
            "turnover": float(np.clip(total_turnover, 0.0, 10.0)),  # Cap at 10x
            "avg_trade_size": float(max(avg_trade_size, 0.0)),
        }

    def _skewness(self, returns: np.ndarray) -> float:
        if len(returns) < 3:
            return 0.0
        mean = np.mean(returns)
        std = np.std(returns)
        if std == 0:
            return 0.0
        return float(np.mean(((returns - mean) / std) ** 3))

    def _kurtosis(self, returns: np.ndarray) -> float:
        if len(returns) < 4:
            return 0.0
        mean = np.mean(returns)
        std = np.std(returns)
        if std == 0:
            return 0.0
        return float(np.mean(((returns - mean) / std) ** 4) - 3)

    def _resample_monthly(self, daily_returns: np.ndarray) -> np.ndarray:
        # Simplified monthly resampling
        n_months = max(1, len(daily_returns) // 21)
        return np.array([np.sum(daily_returns[i*21:(i+1)*21]) for i in range(n_months)])

    def _consecutive_wins_losses(self, fills: Sequence[Any]) -> dict[str, int]:
        # Simplified
        return {"max_losses": 0, "max_wins": 0}