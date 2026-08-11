"""Tests for Walk-Forward and OOS (Phase 9.6)."""

from __future__ import annotations

import os
os.environ.setdefault("AIOS_ENVIRONMENT", "testing")

from datetime import date, datetime, timezone, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aios.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    PaperFill,
    PerformanceSnapshot,
    RiskMetrics,
    WalkForwardMode,
    WalkForwardWindow,
    WalkForwardResult,
    OOSValidationResult,
)
from aios.backtest.evaluation import WalkForwardAnalyzer, OutOfSampleValidator
from aios.config import load_settings


class TestWalkForwardAnalyzer:
    """Tests for WalkForwardAnalyzer."""

    @pytest.fixture
    def backtest_config(self):
        """Create a backtest config with enough data for walk-forward."""
        return BacktestConfig(
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )

    @pytest.fixture
    def mock_data_service(self):
        """Create a mock data service."""
        return MagicMock()

    def test_generate_windows_rolling(self, backtest_config, mock_data_service):
        """Test rolling window generation."""
        from aios.config.settings import WalkForwardSettings

        settings = load_settings()
        settings.walk_forward = WalkForwardSettings(
            train_window_days=252,
            test_window_days=63,
            step_days=63,
            mode="rolling",
        )

        analyzer = WalkForwardAnalyzer(settings)
        windows = analyzer._generate_windows(backtest_config)

        assert len(windows) > 0
        for train_start, train_end, test_start, test_end in windows:
            assert train_start < train_end
            assert train_end < test_start
            assert test_start < test_end
            assert (train_end - train_start).days >= 251  # ~252 days
            assert (test_end - test_start).days >= 62   # ~63 days

    def test_generate_windows_expanding(self, backtest_config, mock_data_service):
        """Test expanding window generation."""
        from aios.config.settings import WalkForwardSettings

        settings = load_settings()
        settings.walk_forward = WalkForwardSettings(
            train_window_days=252,
            test_window_days=63,
            step_days=63,
            mode="expanding",
        )

        analyzer = WalkForwardAnalyzer(settings)
        windows = analyzer._generate_windows(backtest_config)

        assert len(windows) > 0
        # In expanding mode, training start should be fixed
        train_starts = [w[0] for w in windows]
        assert all(ts == train_starts[0] for ts in train_starts)


class TestOutOfSampleValidator:
    """Tests for OutOfSampleValidator."""

    @pytest.fixture
    def backtest_config(self):
        return BacktestConfig(
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=100_000.0,
        )

    def test_valid_split(self, backtest_config):
        """Test validation of a correct train/test split."""
        from aios.config.settings import OutOfSampleSettings

        settings = load_settings()
        settings.oos = OutOfSampleSettings(
            strict_temporal_ordering=True,
            reject_on_overlap=True,
        )

        validator = OutOfSampleValidator(settings)
        result = validator.validate_split(
            backtest_config,
            train_end=date(2022, 12, 31),
            test_start=date(2023, 1, 1),
        )

        assert result.is_valid is True
        assert result.overlap_detected is False
        assert result.look_ahead_detected is False

    def test_overlapping_split_rejected(self, backtest_config):
        """Test that overlapping train/test is rejected."""
        from aios.config.settings import OutOfSampleSettings

        settings = load_settings()
        settings.oos = OutOfSampleSettings(
            strict_temporal_ordering=True,
            reject_on_overlap=True,
        )

        validator = OutOfSampleValidator(settings)
        result = validator.validate_split(
            backtest_config,
            train_end=date(2023, 6, 30),
            test_start=date(2023, 1, 1),  # Overlap!
        )

        assert result.is_valid is False
        assert result.overlap_detected is True
        assert len(result.violations) > 0

    def test_insufficient_train_data(self, backtest_config):
        """Test that insufficient training data is flagged."""
        from aios.config.settings import OutOfSampleSettings

        settings = load_settings()
        settings.oos = OutOfSampleSettings(
            strict_temporal_ordering=True,
            reject_on_overlap=True,
        )

        validator = OutOfSampleValidator(settings)
        result = validator.validate_split(
            backtest_config,
            train_end=date(2020, 2, 1),  # Only ~30 days
            test_start=date(2020, 2, 2),
        )

        assert result.is_valid is False
        assert any("training" in v.lower() for v in result.violations)

    def test_insufficient_test_data(self, backtest_config):
        """Test that insufficient test data is flagged."""
        from aios.config.settings import OutOfSampleSettings

        settings = load_settings()
        settings.oos = OutOfSampleSettings(
            strict_temporal_ordering=True,
            reject_on_overlap=True,
        )

        validator = OutOfSampleValidator(settings)
        result = validator.validate_split(
            backtest_config,
            train_end=date(2023, 12, 15),
            test_start=date(2023, 12, 16),  # Only ~15 days
        )

        assert result.is_valid is False
        assert any("test" in v.lower() for v in result.violations)

    def test_no_lookahead_validation(self, backtest_config):
        """Test validation that test config doesn't use train data."""
        from aios.config.settings import OutOfSampleSettings

        settings = load_settings()
        settings.oos = OutOfSampleSettings()

        validator = OutOfSampleValidator(settings)

        train_config = BacktestConfig(
            start_date=date(2020, 1, 1),
            end_date=date(2022, 12, 31),
            universe=["AAPL", "MSFT"],
        )
        test_config = BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            universe=["AAPL", "MSFT", "GOOGL"],  # Extra symbol
        )

        result = validator.validate_no_lookahead(train_config, test_config)
        assert result.is_valid is False
        assert any("universe" in v.lower() for v in result.violations)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])