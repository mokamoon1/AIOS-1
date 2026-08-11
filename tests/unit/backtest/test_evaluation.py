"""Tests for Strategy Evaluator (Phase 9.6)."""

from __future__ import annotations

import os
os.environ.setdefault("AIOS_ENVIRONMENT", "testing")

from datetime import datetime, timezone, timedelta, date
from uuid import UUID, uuid4

import pytest

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    PaperFill,
    PerformanceSnapshot,
    RiskMetrics,
    FillPolicy,
    SlippageModel,
    TransactionCostConfig,
    StrategyClassification,
)
from aios.backtest.evaluation import StrategyEvaluator
from aios.brokers.models import OrderSide, OrderStatus


class TestStrategyEvaluator:
    """Tests for StrategyEvaluator."""

    @pytest.fixture
    def sample_backtest_result(self) -> BacktestResult:
        """Create a sample backtest result for testing."""
        config = BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )

        # Create equity curve with positive returns
        equity_curve = []
        base_equity = 100_000.0
        for i in range(252):
            daily_return = 0.0005  # ~12.6% annual
            base_equity *= (1 + daily_return)
            equity_curve.append(EquityPoint(
                timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                equity=base_equity,
                cash=base_equity * 0.1,
                market_value=base_equity * 0.9,
                daily_return=daily_return,
                cumulative_return=(base_equity - 100_000.0) / 100_000.0,
            ))

        # Create some fills
        fills = [
            PaperFill(
                fill_id="fill1",
                order_id="order1",
                broker_id="backtest",
                symbol="AAPL",
                exchange="NASDAQ",
                side=OrderSide.BUY,
                quantity=100.0,
                price=150.0,
                realized_pnl=0.0,
            ),
            PaperFill(
                fill_id="fill2",
                order_id="order1",
                broker_id="backtest",
                symbol="AAPL",
                exchange="NASDAQ",
                side=OrderSide.SELL,
                quantity=100.0,
                price=165.0,
                realized_pnl=1500.0,
            ),
        ]

        performance = PerformanceSnapshot(
            total_return=0.15,
            annualized_return=0.15,
            cagr=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=3.0,
            max_drawdown=0.05,
            avg_drawdown=0.02,
            max_drawdown_duration_days=10,
            recovery_time_days=5,
            win_rate=0.6,
            loss_rate=0.4,
            profit_factor=1.8,
            expectancy=50.0,
            avg_holding_period_days=5.0,
            avg_exposure=0.8,
            max_exposure=0.95,
            avg_position_concentration=0.1,
            max_position_concentration=0.2,
            avg_sector_concentration=0.15,
            max_sector_concentration=0.25,
            portfolio_turnover=2.0,
            avg_trade_size=15000.0,
            total_trades=20,
            total_fees_paid=500.0,
        )

        risk_metrics = RiskMetrics(
            var_95=-0.02,
            var_99=-0.03,
            cvar_95=-0.025,
            cvar_99=-0.035,
            skewness=0.1,
            kurtosis=3.2,
            worst_day=-0.03,
            worst_month=-0.08,
            max_consecutive_losses=3,
            max_consecutive_wins=5,
            max_leverage=1.0,
            avg_leverage=1.0,
        )

        return BacktestResult(
            config=config,
            started_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
            equity_curve=equity_curve,
            fills=fills,
            performance=performance,
            risk_metrics=risk_metrics,
        )

    def test_evaluate_returns_result(self, sample_backtest_result):
        """Test that evaluator returns a complete evaluation result."""
        evaluator = StrategyEvaluator()
        result = evaluator.evaluate(sample_backtest_result)

        assert result is not None
        assert result.backtest_id is not None
        assert result.performance is not None
        assert result.risk_metrics is not None
        assert result.classification is not None
        assert isinstance(result.classification, StrategyClassification)

    def test_evaluation_has_score(self, sample_backtest_result):
        """Test that evaluation includes a score."""
        evaluator = StrategyEvaluator()
        result = evaluator.evaluate(sample_backtest_result)

        assert result.score is not None
        assert 0 <= result.score.total_score <= 100
        assert "return" in result.score.breakdown
        assert "risk" in result.score.breakdown

    def test_evaluation_warnings_for_insufficient_data(self):
        """Test that evaluator warns about insufficient data."""
        config = BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
        )
        # Empty equity curve
        result = BacktestResult(
            config=config,
            started_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
            equity_curve=[],
            fills=[],
            performance=PerformanceSnapshot(
                total_return=0.0, annualized_return=0.0, cagr=0.0,
                sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
                max_drawdown=0.0, avg_drawdown=0.0, max_drawdown_duration_days=0,
                recovery_time_days=0, win_rate=0.0, loss_rate=0.0,
                profit_factor=0.0, expectancy=0.0, avg_holding_period_days=0.0,
                avg_exposure=0.0, max_exposure=0.0, avg_position_concentration=0.0,
                max_position_concentration=0.0, avg_sector_concentration=0.0,
                max_sector_concentration=0.0, portfolio_turnover=0.0,
                avg_trade_size=0.0, total_trades=0, total_fees_paid=0.0,
            ),
            risk_metrics=RiskMetrics(
                var_95=0.0, var_99=0.0, cvar_95=0.0, cvar_99=0.0,
                skewness=0.0, kurtosis=0.0, worst_day=0.0, worst_month=0.0,
                max_consecutive_losses=0, max_consecutive_wins=0,
                max_leverage=1.0, avg_leverage=1.0,
            ),
        )

        evaluator = StrategyEvaluator()
        eval_result = evaluator.evaluate(result)

        assert len(eval_result.warnings) > 0
        assert any("insufficient" in w.lower() for w in eval_result.warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])