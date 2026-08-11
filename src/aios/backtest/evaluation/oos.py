"""Out-of-Sample Validation (Phase 9.6)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from aios.backtest.models import (
    BacktestConfig,
    OOSValidationResult,
)
from aios.config import load_settings


class OutOfSampleValidator:
    """Validates that out-of-sample data is properly isolated from training data."""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or load_settings()
        self._oos_settings = self._settings.oos

    def validate_split(
        self,
        config: BacktestConfig,
        train_end: date,
        test_start: date,
    ) -> OOSValidationResult:
        """Validate that train/test split is temporally correct."""
        violations: list[str] = []

        # Check 1: Training ends before test starts
        if train_end >= test_start:
            violations.append(
                f"Training period end ({train_end}) must be before "
                f"test period start ({test_start})"
            )

        # Check 2: No gap or overlap based on settings
        gap_days = (test_start - train_end).days
        if gap_days < 1:
            violations.append(
                f"Gap between train end and test start is {gap_days} days, "
                f"must be at least 1 day"
            )

        # Check 3: Sufficient training data
        train_days = (train_end - config.start_date).days + 1
        if train_days < 50:
            violations.append(
                f"Training period has only {train_days} days, "
                f"minimum recommended is 50"
            )

        # Check 4: Sufficient test data
        test_days = (config.end_date - test_start).days + 1
        if test_days < 20:
            violations.append(
                f"Test period has only {test_days} days, "
                f"minimum recommended is 20"
            )

        # Check 5: Test period is in the future relative to training
        # (already covered by train_end < test_start)

        is_valid = len(violations) == 0

        # Strict mode: any violation makes it invalid
        if self._oos_settings.strict_temporal_ordering and not is_valid:
            if self._oos_settings.reject_on_overlap:
                return OOSValidationResult(
                    is_valid=False,
                    train_end=train_end,
                    test_start=test_start,
                    overlap_detected=True,
                    look_ahead_detected=False,
                    violations=violations,
                )

        return OOSValidationResult(
            is_valid=is_valid,
            train_end=train_end,
            test_start=test_start,
            overlap_detected=not is_valid,
            look_ahead_detected=any(
                "future" in v.lower() or "look" in v.lower() for v in violations
            ),
            violations=violations,
        )

    def validate_no_lookahead(
        self,
        train_config: BacktestConfig,
        test_config: BacktestConfig,
    ) -> OOSValidationResult:
        """Validate that test configuration doesn't use training-period information."""
        violations: list[str] = []

        # Check that test period starts after train period ends
        if test_config.start_date <= train_config.end_date:
            violations.append(
                f"Test start date ({test_config.start_date}) is not after "
                f"train end date ({train_config.end_date})"
            )

        # Check universe consistency (should be same or subset)
        test_universe = set(test_config.universe)
        train_universe = set(train_config.universe)
        if not test_universe.issubset(train_universe):
            violations.append(
                "Test universe contains symbols not in training universe"
            )

        # Check that transaction costs are consistent
        if train_config.transaction_costs != test_config.transaction_costs:
            violations.append(
                "Transaction costs differ between train and test periods"
            )

        return OOSValidationResult(
            is_valid=len(violations) == 0,
            train_end=train_config.end_date,
            test_start=test_config.start_date,
            overlap_detected=False,
            look_ahead_detected=len(violations) > 0,
            violations=violations,
        )

    def validate_oos_fraction(self, config: BacktestConfig) -> OOSValidationResult:
        """Validate that OOS fraction is reasonable for the data period."""
        violations: list[str] = []
        total_days = (config.end_date - config.start_date).days

        oos_days = int(total_days * self._oos_settings.oos_fraction)
        if oos_days < self._oos_settings.min_oos_days:
            violations.append(
                f"OOS period ({oos_days} days) is less than minimum "
                f"({self._oos_settings.min_oos_days} days)"
            )

        train_days = total_days - oos_days
        if train_days < 100:
            violations.append(
                f"Training period ({train_days} days) is too short "
                f"for reliable optimization"
            )

        return OOSValidationResult(
            is_valid=len(violations) == 0,
            train_end=config.start_date + timedelta(days=train_days),
            test_start=config.end_date - timedelta(days=oos_days),
            overlap_detected=False,
            look_ahead_detected=False,
            violations=violations,
        )


from datetime import timedelta  # noqa: E402