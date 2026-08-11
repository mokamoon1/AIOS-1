"""Benchmark comparison engine (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

import numpy as np

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    BenchmarkResult,
    BenchmarkType,
    EquityPoint,
    PaperFill,
    PerformanceSnapshot,
)
from aios.backtest.data import BacktestDataService
from aios.config import load_settings
from aios.data.models import Candle, Timeframe


class BuyHoldCalculator:
    """Calculates buy-and-hold benchmark for a given symbol and period."""

    def __init__(self, data_service: BacktestDataService, config: BacktestConfig):
        self._data_service = data_service
        self._config = config

    def calculate(self, symbol: str, initial_cash: float | None = None) -> PerformanceSnapshot:
        """Calculate buy-and-hold performance for a single symbol."""
        cash = initial_cash or self._config.initial_cash

        # Get all candles for the symbol during the backtest period
        candles = self._data_service.get_candles(
            symbol=symbol,
            timeframe=Timeframe.ONE_DAY,
            limit=10000,
        )

        if not candles or len(candles) < 2:
            return self._empty_performance()

        # Buy at first close, hold until end
        first_close = candles[0].close
        last_close = candles[-1].close

        if first_close <= 0:
            return self._empty_performance()

        quantity = cash / first_close
        final_value = quantity * last_close

        # Daily returns
        daily_returns = []
        for i in range(1, len(candles)):
            prev = candles[i - 1].close
            curr = candles[i].close
            if prev > 0:
                daily_returns.append((curr - prev) / prev)

        daily_returns = np.array(daily_returns)

        # Compute metrics
        total_return = (final_value - cash) / cash
        years = (candles[-1].timestamp - candles[0].timestamp).days / 365.25
        cagr = (1 + total_return) ** (1 / max(years, 1 / 365)) - 1 if years > 0 else 0.0

        # Risk metrics
        sharpe = self._sharpe(daily_returns)
        sortino = self._sortino(daily_returns)

        # Drawdown
        equity_curve = self._build_equity_curve(candles, cash, quantity)
        max_dd, max_dd_dur, avg_dd, recovery = self._drawdowns(equity_curve)

        calmar = cagr / max_dd if max_dd > 0 else 0.0

        return PerformanceSnapshot(
            total_return=total_return,
            annualized_return=cagr,
            cagr=cagr,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            avg_drawdown=avg_dd,
            max_drawdown_duration_days=max_dd_dur,
            recovery_time_days=recovery,
            win_rate=0.0,  # N/A for buy & hold
            loss_rate=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            avg_holding_period_days=years * 365.25,
            avg_exposure=1.0,
            max_exposure=1.0,
            avg_position_concentration=1.0,
            max_position_concentration=1.0,
            avg_sector_concentration=0.0,
            max_sector_concentration=0.0,
            portfolio_turnover=0.0,
            avg_trade_size=0.0,
            total_trades=0,
            total_fees_paid=0.0,
        )

    def _build_equity_curve(
        self, candles: Sequence[Candle], initial_cash: float, quantity: float
    ) -> np.ndarray:
        """Build equity curve for buy and hold."""
        equity = []
        for c in candles:
            equity.append(initial_cash * (c.close / candles[0].close))
        return np.array(equity)

    def _empty_performance(self) -> PerformanceSnapshot:
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

    def _sharpe(self, returns: np.ndarray) -> float:
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(returns) * np.sqrt(252))

    def _sortino(self, returns: np.ndarray) -> float:
        if len(returns) < 2:
            return 0.0
        downside = returns[returns < 0]
        if len(downside) == 0 or np.std(downside) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(downside) * np.sqrt(252))

    def _drawdowns(
        self, equity: np.ndarray
    ) -> tuple[float, int, float, int]:
        peak = equity[0]
        max_dd = 0.0
        max_dur = 0
        cur_dur = 0
        dds = []

        for v in equity:
            if v > peak:
                peak = v
                if cur_dur > 0:
                    dds.append(cur_dur)
                cur_dur = 0
            else:
                dd = (peak - v) / peak if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                cur_dur += 1

        if cur_dur > 0:
            dds.append(cur_dur)

        avg_dd = np.mean([(peak - v) / peak if peak > 0 else 0.0 for v in equity])
        max_dur = max(dds) if dds else 0
        recovery = int(np.mean(dds)) if dds else 0

        return max_dd, max_dur, float(avg_dd), recovery


class BenchmarkEngine:
    """Compares strategy performance against benchmarks."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._bench_settings = self._settings.benchmark

    def compare(
        self,
        strategy_result: BacktestResult,
        benchmark_symbol: str | None = None,
        benchmark_type: BenchmarkType = BenchmarkType.BUY_HOLD,
        data_service: BacktestDataService | None = None,
    ) -> BenchmarkResult:
        """Compare strategy against a benchmark."""
        symbol = benchmark_symbol or self._bench_settings.default_symbol

        # Get strategy metrics
        strat_perf = strategy_result.performance

        if benchmark_type == BenchmarkType.BUY_HOLD:
            if data_service is None:
                raise ValueError("BacktestDataService required for buy-hold benchmark")

            calc = BuyHoldCalculator(data_service, strategy_result.config)
            bench_perf = calc.calculate(symbol)

            return BenchmarkResult(
                benchmark_type=BenchmarkType.BUY_HOLD,
                benchmark_symbol=symbol,
                benchmark_return=bench_perf.total_return,
                benchmark_cagr=bench_perf.cagr,
                benchmark_volatility=self._volatility_from_returns(bench_perf),
                benchmark_sharpe=bench_perf.sharpe_ratio,
                benchmark_max_drawdown=bench_perf.max_drawdown,
                strategy_return=strat_perf.total_return,
                strategy_cagr=strat_perf.cagr,
                strategy_volatility=self._volatility_from_returns(strat_perf),
                strategy_sharpe=strat_perf.sharpe_ratio,
                strategy_max_drawdown=strat_perf.max_drawdown,
                excess_return=strat_perf.total_return - bench_perf.total_return,
                excess_cagr=strat_perf.cagr - bench_perf.cagr,
                tracking_error=self._tracking_error(strategy_result, bench_perf),
                information_ratio=self._information_ratio(
                    strat_perf, bench_perf
                ),
                beta=None,
                correlation=None,
            )

        # For other benchmark types, return placeholder with strategy data only
        return BenchmarkResult(
            benchmark_type=benchmark_type,
            benchmark_symbol=symbol,
            benchmark_return=0.0,
            benchmark_cagr=0.0,
            benchmark_volatility=0.0,
            benchmark_sharpe=0.0,
            benchmark_max_drawdown=0.0,
            strategy_return=strat_perf.total_return,
            strategy_cagr=strat_perf.cagr,
            strategy_volatility=self._volatility_from_returns(strat_perf),
            strategy_sharpe=strat_perf.sharpe_ratio,
            strategy_max_drawdown=strat_perf.max_drawdown,
            excess_return=strat_perf.total_return,
            excess_cagr=strat_perf.cagr,
            tracking_error=None,
            information_ratio=None,
            beta=None,
            correlation=None,
        )

    def _volatility_from_returns(self, perf: PerformanceSnapshot) -> float:
        """Extract volatility from performance snapshot."""
        # Sharpe = return / volatility (assuming risk-free = 0)
        if perf.sharpe_ratio != 0 and perf.annualized_return != 0:
            return perf.annualized_return / perf.sharpe_ratio
        return 0.0

    def _tracking_error(
        self, strategy_result: BacktestResult, bench_perf: PerformanceSnapshot
    ) -> float | None:
        """Calculate tracking error between strategy and benchmark."""
        # Would need daily returns of both; placeholder for now
        return None

    def _information_ratio(
        self, strat: PerformanceSnapshot, bench: PerformanceSnapshot
    ) -> float | None:
        """Calculate information ratio."""
        # Would need return series difference; placeholder
        return None