"""Tests for Phase 9.6 Configuration and Persistence."""

from __future__ import annotations

import os
os.environ.setdefault("AIOS_ENVIRONMENT", "testing")

from datetime import date, datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

import pytest

from aios.config import load_settings
from aios.config.settings import (
    StrategyEvaluationSettings,
    BenchmarkSettings,
    WalkForwardSettings,
    OutOfSampleSettings,
    SensitivitySettings,
    RobustnessSettings,
    MonteCarloSettings,
    StatisticalValidationSettings,
    StrategyScoringSettings,
    StrategyClassificationSettings,
)
from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    BacktestStatus,
    PerformanceSnapshot,
    RiskMetrics,
    EquityPoint,
    PaperFill,
    StrategyEvaluationResult,
)
from aios.database.repositories.backtest import BacktestRepository
from aios.data.services import DataService
from unittest.mock import MagicMock


class TestPhase96Configuration:
    """Tests for Phase 9.6 configuration loading."""

    def test_strategy_evaluation_settings_defaults(self):
        """Test default strategy evaluation settings."""
        settings = load_settings()
        assert hasattr(settings, 'strategy_evaluation')
        assert isinstance(settings.strategy_evaluation, StrategyEvaluationSettings)
        assert settings.strategy_evaluation.risk_free_rate == 0.0
        assert settings.strategy_evaluation.min_trades_for_significance == 30
        assert settings.strategy_evaluation.confidence_level == 0.95

    def test_benchmark_settings_defaults(self):
        """Test default benchmark settings."""
        settings = load_settings()
        assert hasattr(settings, 'benchmark')
        assert isinstance(settings.benchmark, BenchmarkSettings)
        assert settings.benchmark.default_symbol == "SPY"
        assert settings.benchmark.buy_hold_symbol == "SPY"

    def test_walk_forward_settings_defaults(self):
        """Test default walk-forward settings."""
        settings = load_settings()
        assert hasattr(settings, 'walk_forward')
        assert isinstance(settings.walk_forward, WalkForwardSettings)
        assert settings.walk_forward.train_window_days == 252
        assert settings.walk_forward.test_window_days == 63
        assert settings.walk_forward.mode == "rolling"

    def test_oos_settings_defaults(self):
        """Test default OOS settings."""
        settings = load_settings()
        assert hasattr(settings, 'oos')
        assert isinstance(settings.oos, OutOfSampleSettings)
        assert settings.oos.oos_fraction == 0.3
        assert settings.oos.strict_temporal_ordering is True

    def test_sensitivity_settings_defaults(self):
        """Test default sensitivity settings."""
        settings = load_settings()
        assert hasattr(settings, 'sensitivity')
        assert isinstance(settings.sensitivity, SensitivitySettings)
        assert settings.sensitivity.max_combinations == 100
        assert settings.sensitivity.optimization_metric == "sharpe_ratio"

    def test_robustness_settings_defaults(self):
        """Test default robustness settings."""
        settings = load_settings()
        assert hasattr(settings, 'robustness')
        assert isinstance(settings.robustness, RobustnessSettings)
        assert 1.0 in settings.robustness.commission_multipliers
        assert 2.0 in settings.robustness.commission_multipliers

    def test_monte_carlo_settings_defaults(self):
        """Test default Monte Carlo settings."""
        settings = load_settings()
        assert hasattr(settings, 'monte_carlo')
        assert isinstance(settings.monte_carlo, MonteCarloSettings)
        assert settings.monte_carlo.iterations == 10000
        assert settings.monte_carlo.seed == 42

    def test_statistical_validation_settings_defaults(self):
        """Test default statistical validation settings."""
        settings = load_settings()
        assert hasattr(settings, 'statistical_validation')
        assert isinstance(settings.statistical_validation, StatisticalValidationSettings)
        assert settings.statistical_validation.min_trades_for_sharpe == 30

    def test_strategy_scoring_settings_defaults(self):
        """Test default strategy scoring settings."""
        settings = load_settings()
        assert hasattr(settings, 'strategy_scoring')
        assert isinstance(settings.strategy_scoring, StrategyScoringSettings)
        # Weights should sum to 1.0
        weights_sum = (
            settings.strategy_scoring.return_weight +
            settings.strategy_scoring.risk_weight +
            settings.strategy_scoring.consistency_weight +
            settings.strategy_scoring.robustness_weight +
            settings.strategy_scoring.oos_weight +
            settings.strategy_scoring.statistical_weight +
            settings.strategy_scoring.benchmark_weight
        )
        assert abs(weights_sum - 1.0) < 0.001

    def test_strategy_classification_settings_defaults(self):
        """Test default strategy classification settings."""
        settings = load_settings()
        assert hasattr(settings, 'strategy_classification')
        assert isinstance(settings.strategy_classification, StrategyClassificationSettings)
        assert settings.strategy_classification.fail_threshold == 50.0
        assert settings.strategy_classification.block_on_oos_failure is True


class TestPhase96Persistence:
    """Tests for Phase 9.6 persistence."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from aios.database.base import Base

        engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine)

    def test_backtest_repository_round_trip(self, mock_session_factory):
        """Test that BacktestRepository can save and load runs."""
        repo = BacktestRepository(mock_session_factory)

        config = BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )

        from uuid import uuid4
        run = BacktestRun(
            id=uuid4(),
            config=config,
            status=BacktestStatus.COMPLETED,
        )

        repo.add_run(run)
        loaded = repo.get_run(run.id)

        assert loaded.id == run.id
        assert loaded.config.start_date == config.start_date
        assert loaded.status == BacktestStatus.COMPLETED

    def test_equity_curve_persistence(self, mock_session_factory):
        """Test equity curve persistence."""
        repo = BacktestRepository(mock_session_factory)

        from uuid import uuid4
        run_id = uuid4()

        points = [
            EquityPoint(
                timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
                equity=100_000.0, cash=10_000.0, market_value=90_000.0,
                daily_return=0.0, cumulative_return=0.0,
            ),
            EquityPoint(
                timestamp=datetime(2023, 1, 2, tzinfo=timezone.utc),
                equity=101_000.0, cash=10_000.0, market_value=91_000.0,
                daily_return=0.01, cumulative_return=0.01,
            ),
        ]

        stored = repo.add_equity_points(run_id, points)
        assert stored == 2

        loaded = repo.get_equity_curve(run_id)
        assert len(loaded) == 2
        assert loaded[0].equity == 100_000.0
        assert loaded[1].equity == 101_000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])