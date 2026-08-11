"""Tests for Benchmark and Buy & Hold (Phase 9.6)."""

from __future__ import annotations

import os
os.environ.setdefault("AIOS_ENVIRONMENT", "testing")

from datetime import datetime, timezone, date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    PaperFill,
    PerformanceSnapshot,
    RiskMetrics,
    BenchmarkType,
)
from aios.backtest.evaluation import BuyHoldCalculator, BenchmarkEngine
from aios.brokers.models import OrderSide


class TestBuyHoldCalculator:
    """Tests for BuyHoldCalculator."""

    @pytest.fixture
    def sample_candles(self) -> list:
        """Create sample candle data."""
        from aios.data.models import Candle, Timeframe

        candles = []
        base_price = 100.0
        for i in range(252):
            # Slight uptrend
            base_price *= 1.0005
            candles.append(Candle(
                timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                symbol="SPY",
                timeframe=Timeframe.ONE_DAY,
                open=base_price,
                high=base_price * 1.01,
                low=base_price * 0.99,
                close=base_price,
                volume=1_000_000.0,
            ))
        return candles

    @pytest.fixture
    def mock_data_service(self, sample_candles):
        """Create a mock data service."""
        from unittest.mock import MagicMock

        service = MagicMock()
        service.get_candles.return_value = sample_candles
        return service

    @pytest.fixture
    def backtest_config(self):
        """Create a backtest config."""
        return BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )

    def test_buy_hold_calculates_correct_return(self, mock_data_service, backtest_config):
        """Test that buy-hold calculates correct total return."""
        calc = BuyHoldCalculator(mock_data_service, backtest_config)
        result = calc.calculate("SPY")

        # With 0.05% daily return over 252 days, total return ~12.6%
        assert result.total_return > 0.10
        assert result.total_return < 0.20
        assert result.cagr > 0.10
        assert result.sharpe_ratio > 0

    def test_buy_hold_with_insufficient_data(self, mock_data_service, backtest_config):
        """Test buy-hold with insufficient data returns empty performance."""
        from aios.data.models import Candle, Timeframe

        mock_data_service.get_candles.return_value = [
            Candle(
                timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
                symbol="SPY",
                timeframe=Timeframe.ONE_DAY,
                open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0,
            )
        ]

        calc = BuyHoldCalculator(mock_data_service, backtest_config)
        result = calc.calculate("SPY")

        assert result.total_return == 0.0
        assert result.cagr == 0.0


class TestBenchmarkEngine:
    """Tests for BenchmarkEngine."""

    @pytest.fixture
    def sample_backtest_result(self) -> BacktestResult:
        """Create a sample backtest result."""
        config = BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )

        performance = PerformanceSnapshot(
            total_return=0.20,
            annualized_return=0.20,
            cagr=0.20,
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
            var_95=-0.02, var_99=-0.03, cvar_95=-0.025, cvar_99=-0.035,
            skewness=0.1, kurtosis=3.2, worst_day=-0.03, worst_month=-0.08,
            max_consecutive_losses=3, max_consecutive_wins=5,
            max_leverage=1.0, avg_leverage=1.0,
        )

        return BacktestResult(
            config=config,
            started_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
            equity_curve=[],
            fills=[],
            performance=performance,
            risk_metrics=risk_metrics,
        )

    @pytest.fixture
    def mock_data_service(self):
        """Create a mock data service with buy-hold returning known values."""
        from unittest.mock import MagicMock
        from aios.backtest.models import PerformanceSnapshot

        service = MagicMock()

        # Mock buy-hold performance
        bh_perf = PerformanceSnapshot(
            total_return=0.10,
            annualized_return=0.10,
            cagr=0.10,
            sharpe_ratio=0.8,
            sortino_ratio=1.0,
            calmar_ratio=2.0,
            max_drawdown=0.05,
            avg_drawdown=0.02,
            max_drawdown_duration_days=15,
            recovery_time_days=10,
            win_rate=0.0, loss_rate=0.0, profit_factor=0.0,
            expectancy=0.0, avg_holding_period_days=365.0,
            avg_exposure=1.0, max_exposure=1.0,
            avg_position_concentration=1.0, max_position_concentration=1.0,
            avg_sector_concentration=0.0, max_sector_concentration=0.0,
            portfolio_turnover=0.0, avg_trade_size=0.0,
            total_trades=0, total_fees_paid=0.0,
        )

        calculator = MagicMock()
        calculator.calculate.return_value = bh_perf
        service.get_calculator = lambda: calculator

        return service

    def test_benchmark_comparison(self, sample_backtest_result, mock_data_service):
        """Test benchmark comparison produces valid result."""
        from aios.backtest.evaluation import BuyHoldCalculator
        from unittest.mock import patch

        # Mock the BuyHoldCalculator used internally
        with patch('aios.backtest.evaluation.benchmark.BuyHoldCalculator') as mock_calc_class:
            mock_calc = MagicMock()
            mock_calc.calculate.return_value = PerformanceSnapshot(
                total_return=0.10,
                annualized_return=0.10,
                cagr=0.10,
                sharpe_ratio=0.8,
                sortino_ratio=1.0,
                calmar_ratio=2.0,
                max_drawdown=0.05,
                avg_drawdown=0.02,
                max_drawdown_duration_days=15,
                recovery_time_days=10,
                win_rate=0.0, loss_rate=0.0, profit_factor=0.0,
                expectancy=0.0, avg_holding_period_days=365.0,
                avg_exposure=1.0, max_exposure=1.0,
                avg_position_concentration=1.0, max_position_concentration=1.0,
                avg_sector_concentration=0.0, max_sector_concentration=0.0,
                portfolio_turnover=0.0, avg_trade_size=0.0,
                total_trades=0, total_fees_paid=0.0,
            )
            mock_calc_class.return_value = mock_calc

            engine = BenchmarkEngine()
            result = engine.compare(
                sample_backtest_result,
                benchmark_symbol="SPY",
                benchmark_type=BenchmarkType.BUY_HOLD,
                data_service=mock_data_service,
            )

        assert result is not None
        assert result.benchmark_type == BenchmarkType.BUY_HOLD
        assert result.strategy_return == 0.20
        assert result.benchmark_return == 0.10
        assert result.excess_return == 0.10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])