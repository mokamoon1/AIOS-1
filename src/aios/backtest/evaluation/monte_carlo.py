"""Monte Carlo Simulation (Phase 9.6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import numpy as np

from aios.backtest.models import (
    BacktestResult,
    MonteCarloResult,
    PaperFill,
)
from aios.config import load_settings


class MonteCarloEngine:
    """Runs Monte Carlo simulations on backtest results."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._mc_settings = self._settings.monte_carlo

    def simulate(
        self,
        result: BacktestResult,
        seed: int | None = None,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation on trade sequence."""
        seed = seed or self._mc_settings.seed
        np.random.seed(seed)

        # Extract trade P&Ls
        trade_pnls = self._extract_trade_pnls(result.fills)
        if len(trade_pnls) < 2:
            return self._empty_result(seed)

        initial_equity = result.equity_curve[0].equity if result.equity_curve else 100000.0

        # Run simulations
        returns = []
        max_drawdowns = []
        final_equities = []

        for _ in range(self._mc_settings.iterations):
            if self._mc_settings.shuffle_trades:
                # Shuffle trade sequence
                shuffled = np.random.permutation(trade_pnls)
            else:
                shuffled = trade_pnls

            # Simulate equity curve
            equity = initial_equity
            equity_curve = [equity]
            for pnl in shuffled:
                equity += pnl
                equity_curve.append(equity)

            equity_curve = np.array(equity_curve)
            total_return = (equity - initial_equity) / initial_equity
            max_dd = self._max_drawdown(equity_curve)

            returns.append(total_return)
            max_drawdowns.append(max_dd)
            final_equities.append(equity)

        returns = np.array(returns)
        max_drawdowns = np.array(max_drawdowns)

        # Calculate percentiles
        percentiles = {}
        for p in self._mc_settings.confidence_levels:
            percentiles[f"p{int(p*100)}"] = float(np.percentile(returns, p * 100))

        # Probability of loss
        prob_loss = float(np.mean(returns < 0))

        # Probability of drawdown exceeding thresholds
        prob_dd = {}
        for thresh in self._mc_settings.drawdown_thresholds:
            prob_dd[thresh] = float(np.mean(max_drawdowns > thresh))

        return MonteCarloResult(
            iterations=self._mc_settings.iterations,
            seed=seed,
            median_return=float(np.median(returns)),
            percentile_5=percentiles.get("p5", 0.0),
            percentile_25=percentiles.get("p25", 0.0),
            percentile_75=percentiles.get("p75", 0.0),
            percentile_95=percentiles.get("p95", 0.0),
            worst_case_return=float(np.min(returns)),
            best_case_return=float(np.max(returns)),
            probability_of_loss=prob_loss,
            probability_of_drawdown_exceeding=prob_dd,
            median_max_drawdown=float(np.median(max_drawdowns)),
            drawdown_distribution=max_drawdowns.tolist(),
        )

    def _extract_trade_pnls(self, fills: Sequence[PaperFill]) -> list[float]:
        """Extract P&L for each completed trade from fills."""
        # Group fills by order
        trades_by_order = {}
        for fill in fills:
            oid = getattr(fill, "order_id", None)
            if oid:
                trades_by_order.setdefault(oid, []).append(fill)

        pnls = []
        for order_fills in trades_by_order.values():
            buy_fills = [f for f in order_fills if getattr(f, "side", None) == "buy"]
            sell_fills = [f for f in order_fills if getattr(f, "side", None) == "sell"]

            if buy_fills and sell_fills:
                # Use first buy and first sell as entry/exit
                entry = buy_fills[0]
                exit = sell_fills[0]
                pnl = getattr(exit, "realized_pnl", 0.0)
                pnls.append(pnl)

        return pnls

    def _max_drawdown(self, equity: np.ndarray) -> float:
        """Calculate maximum drawdown."""
        peak = equity[0]
        max_dd = 0.0
        for v in equity:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _empty_result(self, seed: int) -> MonteCarloResult:
        return MonteCarloResult(
            iterations=self._mc_settings.iterations,
            seed=seed,
            median_return=0.0,
            percentile_5=0.0,
            percentile_25=0.0,
            percentile_75=0.0,
            percentile_95=0.0,
            worst_case_return=0.0,
            best_case_return=0.0,
            probability_of_loss=0.0,
            probability_of_drawdown_exceeding={},
            median_max_drawdown=0.0,
            drawdown_distribution=[],
        )