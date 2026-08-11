"""Tests for Sensitivity, Robustness, Monte Carlo, Validation, Scoring, Classification, Comparison (Phase 9.6)."""

from __future__ import annotations

import os
os.environ.setdefault("AIOS_ENVIRONMENT", "testing")

from datetime import date, datetime, timezone, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    PaperFill,
    PerformanceSnapshot,
    RiskMetrics,
    SensitivityResult,
    RobustnessResult,
    RobustnessScenario,
    MonteCarloResult,
    StatisticalValidationResult,
    StrategyScore,
    StrategyClassification,
    OOSValidationResult,
)
from aios.backtest.evaluation import (
    SensitivityAnalyzer,
    RobustnessAnalyzer,
    MonteCarloEngine,
    StatisticalValidator,
    StrategyScorer,
    StrategyClassifier,
    BacktestComparator,
    ComparisonResult,
)
from aios.config import load_settings


# Fixtures
@pytest.fixture
def sample_backtest_result():
    """Create a sample backtest result."""
    config = BacktestConfig(
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        initial_cash=100_000.0,
    )

    equity_curve = []
    base = 100_000.0
    for i in range(252):
        base *= 1.0005
        equity_curve.append(EquityPoint(
            timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            equity=base, cash=base*0.1, market_value=base*0.9,
            daily_return=0.0005, cumulative_return=(base-100_000)/100_000,
        ))

    fills = [
        PaperFill(fill_id="f1", order_id="o1", broker_id="b", symbol="AAPL", exchange="NASDAQ",
                  side="buy", quantity=100.0, price=150.0, realized_pnl=0.0),
        PaperFill(fill_id="f2", order_id="o1", broker_id="b", symbol="AAPL", exchange="NASDAQ",
                  side="sell", quantity=100.0, price=165.0, realized_pnl=1500.0),
    ]

    performance = PerformanceSnapshot(
        total_return=0.15, annualized_return=0.15, cagr=0.15,
        sharpe_ratio=1.5, sortino_ratio=2.0, calmar_ratio=3.0,
        max_drawdown=0.05, avg_drawdown=0.02, max_drawdown_duration_days=10,
        recovery_time_days=5, win_rate=0.6, loss_rate=0.4,
        profit_factor=1.8, expectancy=50.0, avg_holding_period_days=5.0,
        avg_exposure=0.8, max_exposure=0.95, avg_position_concentration=0.1,
        max_position_concentration=0.2, avg_sector_concentration=0.15,
        max_sector_concentration=0.25, portfolio_turnover=2.0,
        avg_trade_size=15000.0, total_trades=20, total_fees_paid=500.0,
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
        equity_curve=equity_curve,
        fills=fills,
        performance=performance,
        risk_metrics=risk_metrics,
    )


class TestSensitivityAnalyzer:
    """Tests for SensitivityAnalyzer."""

    @pytest.fixture
    def mock_data_service(self):
        return MagicMock()

    def test_analyze_with_parameter_ranges(self, sample_backtest_result, mock_data_service):
        """Test sensitivity analysis with parameter ranges."""
        from aios.config.settings import SensitivitySettings

        settings = load_settings()
        settings.sensitivity = SensitivitySettings(
            parameter_ranges={"param1": [0.1, 0.2, 0.3], "param2": [1.0, 2.0]},
            max_combinations=10,
            optimization_metric="sharpe_ratio",
        )

        analyzer = SensitivityAnalyzer(settings)

        # Mock the backtest run
        with patch.object(analyzer, '_run_backtest', return_value=sample_backtest_result):
            results = analyzer.analyze(
                sample_backtest_result.config,
                mock_data_service,
            )

        assert len(results) == 2  # Two parameters
        for r in results:
            assert r.parameter_name in ["param1", "param2"]
            assert len(r.parameter_values) > 0
            assert len(r.metric_values) > 0
            assert 0 <= r.stability_score <= 1


class TestRobustnessAnalyzer:
    """Tests for RobustnessAnalyzer."""

    @pytest.fixture
    def mock_data_service(self):
        return MagicMock()

    def test_analyze_generates_scenarios(self, sample_backtest_result, mock_data_service):
        """Test that robustness analyzer generates stress scenarios."""
        from aios.config.settings import RobustnessSettings

        settings = load_settings()
        settings.robustness = RobustnessSettings(
            commission_multipliers=[1.0, 1.5],
            spread_multipliers=[1.0, 2.0],
            slippage_multipliers=[1.0],
            execution_delays=[0, 1],
            min_fill_fractions=[0.01],
        )

        analyzer = RobustnessAnalyzer(settings)

        with patch.object(analyzer, '_run_backtest', return_value=sample_backtest_result):
            result = analyzer.analyze(
                sample_backtest_result.config,
                mock_data_service,
                baseline_result=sample_backtest_result,
            )

        assert isinstance(result, RobustnessResult)
        assert result.baseline_performance is not None
        # 2 * 2 * 1 * 2 * 1 = 8 scenarios
        assert len(result.scenarios) == 8
        assert result.worst_case_drawdown >= sample_backtest_result.performance.max_drawdown

    def test_degradation_threshold(self, sample_backtest_result, mock_data_service):
        """Test degradation threshold detection."""
        from aios.config.settings import RobustnessSettings

        settings = load_settings()
        settings.robustness = RobustnessSettings(
            commission_multipliers=[1.0, 10.0],  # Extreme
            spread_multipliers=[1.0],
            slippage_multipliers=[1.0],
            execution_delays=[0],
            min_fill_fractions=[0.01],
            max_return_degradation=0.1,
            max_drawdown_increase=0.1,
        )

        # Create a degraded result
        degraded = BacktestResult(
            config=sample_backtest_result.config,
            started_at=sample_backtest_result.started_at,
            completed_at=sample_backtest_result.completed_at,
            equity_curve=sample_backtest_result.equity_curve,
            fills=sample_backtest_result.fills,
            performance=PerformanceSnapshot(
                total_return=0.01,  # Much worse
                annualized_return=0.01, cagr=0.01,
                sharpe_ratio=0.1, sortino_ratio=0.1, calmar_ratio=0.1,
                max_drawdown=0.30, avg_drawdown=0.15,
                max_drawdown_duration_days=50, recovery_time_days=30,
                win_rate=0.3, loss_rate=0.7, profit_factor=0.8,
                expectancy=-10.0, avg_holding_period_days=5.0,
                avg_exposure=0.8, max_exposure=0.95,
                avg_position_concentration=0.1, max_position_concentration=0.2,
                avg_sector_concentration=0.15, max_sector_concentration=0.25,
                portfolio_turnover=2.0, avg_trade_size=15000.0,
                total_trades=20, total_fees_paid=5000.0,
            ),
            risk_metrics=sample_backtest_result.risk_metrics,
        )

        analyzer = RobustnessAnalyzer(settings)

        with patch.object(analyzer, '_run_backtest', side_effect=[sample_backtest_result, degraded]):
            result = analyzer.analyze(
                sample_backtest_result.config,
                mock_data_service,
                baseline_result=sample_backtest_result,
            )

        assert result.degradation_threshold_exceeded is True


class TestMonteCarloEngine:
    """Tests for MonteCarloEngine."""

    def test_simulate_with_sufficient_trades(self, sample_backtest_result):
        """Test Monte Carlo simulation with sufficient trades."""
        from aios.config.settings import MonteCarloSettings

        settings = load_settings()
        settings.monte_carlo = MonteCarloSettings(
            iterations=1000,
            seed=42,
        )

        engine = MonteCarloEngine(settings)
        result = engine.simulate(sample_backtest_result, seed=42)

        assert isinstance(result, MonteCarloResult)
        assert result.iterations == 1000
        assert result.seed == 42
        assert -1.0 <= result.median_return <= 1.0
        assert 0.0 <= result.probability_of_loss <= 1.0
        assert result.percentile_5 <= result.percentile_25 <= result.percentile_75 <= result.percentile_95

    def test_simulate_deterministic(self, sample_backtest_result):
        """Test that same seed produces same results."""
        from aios.config.settings import MonteCarloSettings

        settings = load_settings()
        settings.monte_carlo = MonteCarloSettings(iterations=1000, seed=123)

        engine = MonteCarloEngine(settings)
        result1 = engine.simulate(sample_backtest_result, seed=123)
        result2 = engine.simulate(sample_backtest_result, seed=123)

        assert result1.median_return == result2.median_return
        assert result1.worst_case_return == result2.worst_case_return


class TestStatisticalValidator:
    """Tests for StatisticalValidator."""

    def test_validate_sufficient_sample(self, sample_backtest_result):
        """Test validation with sufficient sample."""
        from aios.config.settings import StatisticalValidationSettings

        settings = load_settings()
        settings.statistical_validation = StatisticalValidationSettings(
            min_trades_for_sharpe=1,
            min_trades_for_drawdown=1,
            confidence_level=0.95,
        )

        validator = StatisticalValidator(settings)
        result = validator.validate(sample_backtest_result)

        assert isinstance(result, StatisticalValidationResult)
        assert result.trade_count >= 1
        # The fixture only has 1 trade (2 fills for same order), so with min_trades=1 it should be sufficient
        assert result.sufficient_sample is True

    def test_validate_insufficient_trades(self):
        """Test validation with insufficient trades."""
        from aios.config.settings import StatisticalValidationSettings

        config = BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )

        # Only 1 trade
        equity_curve = [EquityPoint(
            timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
            equity=100_000.0, cash=10_000.0, market_value=90_000.0,
            daily_return=0.0, cumulative_return=0.0,
        )]

        result = BacktestResult(
            config=config,
            started_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
            equity_curve=equity_curve,
            fills=[],  # No fills = no trades
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

        settings = load_settings()
        settings.statistical_validation = StatisticalValidationSettings(
            min_trades_for_sharpe=30,
            min_trades_for_drawdown=20,
        )

        validator = StatisticalValidator(settings)
        result = validator.validate(result)

        assert result.sufficient_sample is False
        assert result.is_statistically_significant is False
        assert any("insufficient" in w.lower() for w in result.warnings)


class TestStrategyScorer:
    """Tests for StrategyScorer."""

    def test_score_calculation(self, sample_backtest_result):
        """Test that scoring produces valid scores."""
        from aios.config.settings import StrategyScoringSettings

        settings = load_settings()
        settings.strategy_scoring = StrategyScoringSettings(
            return_weight=0.20, risk_weight=0.20,
            consistency_weight=0.15, robustness_weight=0.15,
            oos_weight=0.15, statistical_weight=0.10,
            benchmark_weight=0.05,
        )

        scorer = StrategyScorer(settings)
        score = scorer.score(
            sample_backtest_result,
            sample_backtest_result.performance,
            sample_backtest_result.risk_metrics,
            None,  # No statistical validation
            None,  # No benchmark
        )

        assert isinstance(score, StrategyScore)
        assert 0 <= score.total_score <= 100
        assert "return" in score.breakdown
        assert "risk" in score.breakdown
        assert "consistency" in score.breakdown


class TestStrategyClassifier:
    """Tests for StrategyClassifier."""

    def test_classify_robust(self, sample_backtest_result):
        """Test classification of a robust strategy."""
        from aios.config.settings import StrategyScoringSettings, StrategyClassificationSettings

        settings = load_settings()
        settings.strategy_scoring = StrategyScoringSettings()
        settings.strategy_classification = StrategyClassificationSettings(
            fail_threshold=50.0, weak_threshold=65.0,
            acceptable_threshold=80.0,
            block_on_oos_failure=False,
            block_on_severe_drawdown=False,
            block_on_insufficient_sample=False,
            block_on_look_ahead=False,
            block_on_nondeterministic=False,
        )

        # Create high score
        score = StrategyScore(
            return_score=90, risk_score=85, consistency_score=80,
            robustness_score=85, oos_score=90, statistical_score=80,
            benchmark_score=75, total_score=85.0,
            breakdown={},
        )

        stat_validation = StatisticalValidationResult(
            sharpe_confidence_interval=(1.0, 2.0),
            return_confidence_interval=(0.001, 0.003),
            max_drawdown_confidence_interval=(0.03, 0.07),
            trade_count=20,
            is_statistically_significant=True,
            warnings=[],
            sufficient_sample=True,
        )

        classifier = StrategyClassifier(settings)
        classification = classifier.classify(score, stat_validation, None)

        assert classification == StrategyClassification.ROBUST

    def test_classify_fail_on_low_score(self):
        """Test that low score results in FAIL."""
        from aios.config.settings import StrategyScoringSettings, StrategyClassificationSettings

        settings = load_settings()
        settings.strategy_scoring = StrategyScoringSettings()
        settings.strategy_classification = StrategyClassificationSettings(
            fail_threshold=50.0, weak_threshold=65.0,
            acceptable_threshold=80.0,
        )

        score = StrategyScore(
            return_score=20, risk_score=20, consistency_score=20,
            robustness_score=20, oos_score=20, statistical_score=20,
            benchmark_score=20, total_score=20.0,
            breakdown={},
        )

        stat_validation = StatisticalValidationResult(
            sharpe_confidence_interval=None, return_confidence_interval=None,
            max_drawdown_confidence_interval=None, trade_count=5,
            is_statistically_significant=False, warnings=[],
            sufficient_sample=False,
        )

        classifier = StrategyClassifier(settings)
        classification = classifier.classify(score, stat_validation, None)

        assert classification == StrategyClassification.FAIL

    def test_blocking_condition_oos_failure(self, sample_backtest_result):
        """Test that OOS failure blocks ROBUST classification."""
        from aios.config.settings import StrategyScoringSettings, StrategyClassificationSettings

        settings = load_settings()
        settings.strategy_scoring = StrategyScoringSettings()
        settings.strategy_classification = StrategyClassificationSettings(
            block_on_oos_failure=True,
            fail_threshold=50.0, weak_threshold=65.0,
            acceptable_threshold=80.0,
        )

        # High score but OOS failure
        score = StrategyScore(
            return_score=90, risk_score=85, consistency_score=80,
            robustness_score=85, oos_score=10, statistical_score=80,
            benchmark_score=75, total_score=85.0,
            breakdown={},
        )

        stat_validation = StatisticalValidationResult(
            sharpe_confidence_interval=(1.0, 2.0), return_confidence_interval=(0.001, 0.003),
            max_drawdown_confidence_interval=(0.03, 0.07), trade_count=20,
            is_statistically_significant=True, warnings=[],
            sufficient_sample=True,
        )

        # Mock result with OOS failure
        from aios.backtest.models import OOSValidationResult
        class MockResult:
            def __init__(self):
                self.evaluation = type('obj', (object,), {
                    'oos_validation': OOSValidationResult(
                        is_valid=False, train_end=date(2022, 12, 31),
                        test_start=date(2023, 1, 1), overlap_detected=True,
                        look_ahead_detected=False, violations=["Overlap"]
                    )
                })()

        classifier = StrategyClassifier(settings)
        classification = classifier.classify(score, stat_validation, MockResult())

        assert classification == StrategyClassification.FAIL


class TestBacktestComparator:
    """Tests for BacktestComparator."""

    def test_compare_multiple_results(self, sample_backtest_result):
        """Test comparison of multiple backtest results."""
        # Create second result with different performance
        config2 = BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )
        result2 = BacktestResult(
            config=config2,
            started_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
            equity_curve=sample_backtest_result.equity_curve,
            fills=sample_backtest_result.fills,
            performance=PerformanceSnapshot(
                total_return=0.08, annualized_return=0.08, cagr=0.08,
                sharpe_ratio=0.8, sortino_ratio=1.0, calmar_ratio=1.5,
                max_drawdown=0.10, avg_drawdown=0.04, max_drawdown_duration_days=20,
                recovery_time_days=15, win_rate=0.5, loss_rate=0.5,
                profit_factor=1.2, expectancy=20.0, avg_holding_period_days=5.0,
                avg_exposure=0.7, max_exposure=0.9, avg_position_concentration=0.15,
                max_position_concentration=0.25, avg_sector_concentration=0.2,
                max_sector_concentration=0.3, portfolio_turnover=1.5,
                avg_trade_size=12000.0, total_trades=15, total_fees_paid=400.0,
            ),
            risk_metrics=sample_backtest_result.risk_metrics,
        )

        comparator = BacktestComparator()
        result = comparator.compare([
            ("Strategy A", sample_backtest_result),
            ("Strategy B", result2),
        ])

        assert isinstance(result, ComparisonResult)
        assert len(result.rankings) == 2
        assert result.best_overall == "Strategy A"  # Higher Sharpe
        assert "Strategy A" in result.comparison_matrix
        assert "Strategy B" in result.comparison_matrix
        assert len(result.notes) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])