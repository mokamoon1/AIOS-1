"""Market Regime Analysis (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    PerformanceSnapshot,
)
from aios.backtest.data import BacktestDataService
from aios.data.models import Candle, Timeframe


class MarketRegimeAnalyzer:
    """Analyzes strategy performance across different market regimes."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings

    def analyze(
        self,
        result: BacktestResult,
        data_service: BacktestDataService,
        benchmark_symbol: str = "SPY",
    ) -> dict[str, PerformanceSnapshot]:
        """Analyze performance by market regime."""
        # Get benchmark data for regime detection
        bench_candles = data_service.get_candles(
            symbol=benchmark_symbol,
            timeframe=Timeframe.ONE_DAY,
            limit=10000,
        )

        if len(bench_candles) < 50:
            return {"unknown": result.performance}

        # Detect regimes
        regimes = self._detect_regimes(bench_candles)

        # Split equity curve by regime
        regime_performances = self._split_by_regime(
            result.equity_curve, bench_candles, regimes
        )

        # Compute performance for each regime
        result_dict = {}
        for regime_name, (equity_points, fills) in regime_performances.items():
            if len(equity_points) > 1:
                from aios.backtest.calculator import PerformanceCalculator

                calc = PerformanceCalculator()
                perf = calc.compute(equity_points, fills, equity_points[0].equity)
                result_dict[regime_name] = perf
            else:
                result_dict[regime_name] = result.performance

        return result_dict

    def _detect_regimes(
        self, candles: Sequence[Candle]
    ) -> list[tuple[datetime, str]]:
        """Detect market regimes from benchmark candles.
        
        Returns list of (timestamp, regime) tuples.
        Regimes: bull, bear, sideways, high_vol, low_vol
        """
        if len(candles) < 50:
            return [(candles[0].timestamp, "unknown")]

        # Calculate rolling metrics
        closes = np.array([c.close for c in candles])
        returns = np.diff(closes) / closes[:-1]

        # 20-day SMA for trend
        sma_20 = self._rolling_sma(closes, 20)
        # 50-day SMA for longer trend
        sma_50 = self._rolling_sma(closes, 50)
        # 20-day volatility
        vol_20 = self._rolling_vol(returns, 20)

        regimes = []
        for i in range(len(candles)):
            if i < 50:
                regimes.append((candles[i].timestamp, "forming"))
                continue

            close = closes[i]
            s20 = sma_20[i] if i < len(sma_20) else close
            s50 = sma_50[i] if i < len(sma_50) else close
            v20 = vol_20[i] if i < len(vol_20) else 0.02

            # Classify regime
            regime = "sideways"
            if close > s20 > s50:
                regime = "bull"
            elif close < s20 < s50:
                regime = "bear"

            # Volatility overlay
            if v20 > 0.03:  # High volatility threshold
                regime = f"{regime}_high_vol"
            elif v20 < 0.01:
                regime = f"{regime}_low_vol"

            regimes.append((candles[i].timestamp, regime))

        return regimes

    def _split_by_regime(
        self,
        equity_curve: list,
        candles: Sequence[Candle],
        regimes: list[tuple],
    ) -> dict[str, tuple[list, list]]:
        """Split equity curve and fills by regime."""
        # This is a simplified version - in practice you'd match
        # equity curve timestamps to regime timestamps
        result = {}
        return result

    def _rolling_sma(self, data: np.ndarray, window: int) -> np.ndarray:
        """Calculate rolling SMA."""
        result = np.full(len(data), np.nan)
        for i in range(window - 1, len(data)):
            result[i] = np.mean(data[i - window + 1 : i + 1])
        return result

    def _rolling_vol(self, returns: np.ndarray, window: int) -> np.ndarray:
        """Calculate rolling volatility."""
        result = np.full(len(returns) + 1, np.nan)  # +1 for alignment
        for i in range(window - 1, len(returns)):
            result[i + 1] = np.std(returns[i - window + 1 : i + 1])
        return result