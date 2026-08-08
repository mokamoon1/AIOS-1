"""Data validation framework tests (AIOS-506)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.data.exceptions import DataValidationError
from aios.data.models import Candle
from aios.data.validation import (
    DataValidator,
    ValidationErrorCode,
    ValidationIssue,
    ValidationResult,
    raise_for_invalid,
)

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestValidationLevels:
    def test_valid_dataset_reports_valid(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles("ds-1", [_valid_candle()])
        assert report.result is ValidationResult.VALID
        assert report.is_valid is True
        assert report.issues == []

    def test_level2_missing_field_reports_invalid(self) -> None:
        validator = DataValidator()
        data = _valid_candle()
        del data["close"]
        report = validator.validate_candles("ds-1", [data])
        assert report.result is ValidationResult.INVALID
        assert report.is_valid is False
        assert report.issues_by_code(ValidationErrorCode.MISSING_DATA)

    def test_level2_invalid_enum_reports_invalid(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles("ds-1", [_valid_candle(timeframe="42m")])
        assert report.result is ValidationResult.INVALID
        assert report.issues_by_code(ValidationErrorCode.INVALID_VALUE)

    def test_level3_high_below_open_reports_invalid(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles("ds-1", [_valid_candle(high=95.0)])
        assert report.result is ValidationResult.INVALID
        assert report.issues_by_code(ValidationErrorCode.CONSISTENCY_ERROR)

    def test_level3_low_above_close_reports_invalid(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles("ds-1", [_valid_candle(low=110.0)])
        assert report.issues_by_code(ValidationErrorCode.CONSISTENCY_ERROR)

    def test_level3_naive_timestamp_reports_timestamp_error(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles(
            "ds-1", [_valid_candle(timestamp="2026-08-01T13:30:00")]
        )
        assert report.result is ValidationResult.INVALID
        assert report.issues_by_code(ValidationErrorCode.TIMESTAMP_ERROR)

    def test_level4_duplicate_detection_warns(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles("ds-1", [_valid_candle(), _valid_candle()])
        assert report.result is ValidationResult.WARNING
        assert report.issues_by_code(ValidationErrorCode.DUPLICATE_RECORD)

    def test_level4_freshness_warns_when_stale(self) -> None:
        stale = _now() - timedelta(days=5)
        validator = DataValidator(freshness_max_age=timedelta(days=1))
        report = validator.validate_candles(
            "ds-1",
            [_valid_candle(timestamp=stale.isoformat().replace("+00:00", "Z"))],
        )
        assert report.result is ValidationResult.WARNING
        assert report.issues_by_code(ValidationErrorCode.INVALID_VALUE)

    def test_freshness_no_warning_when_recent(self) -> None:
        validator = DataValidator(freshness_max_age=timedelta(days=1))
        recent = _now().isoformat().replace("+00:00", "Z")
        report = validator.validate_candles("ds-1", [_valid_candle(timestamp=recent)])
        assert report.result is ValidationResult.VALID


class TestValidatorInjection:
    def test_injected_candle_rule_is_applied(self) -> None:
        class AlwaysReject:
            def validate(self, candle: Candle) -> list[ValidationIssue]:
                return [
                    ValidationIssue(
                        ValidationErrorCode.PROVIDER_ERROR,
                        "injected rule rejected",
                        field="symbol",
                    )
                ]

        validator = DataValidator()
        validator.add_candle_rule(AlwaysReject())
        report = validator.validate_candles("ds-1", [_valid_candle()])
        assert report.result is ValidationResult.INVALID
        assert report.issues_by_code(ValidationErrorCode.PROVIDER_ERROR)


class TestComplianceValidation:
    def _valid(self, **overrides) -> dict:
        base = {
            "symbol": "AAPL",
            "company_name": "Apple Inc.",
            "exchange": "NASDAQ",
            "country": "US",
            "asset_type": "equity",
            "compliance_status": "compliant",
            "provider": "test-provider",
            "review_date": "2026-07-01",
            "effective_date": "2026-07-01",
            "screening_methodology": "test-methodology",
            "screening_date": "2026-07-01",
        }
        base.update(overrides)
        return base

    def test_valid_compliance_record(self) -> None:
        report = DataValidator().validate_compliance("ds-2", [self._valid()])
        assert report.result is ValidationResult.VALID

    def test_expiration_before_effective_is_consistency_error(self) -> None:
        report = DataValidator().validate_compliance(
            "ds-2",
            [self._valid(effective_date="2026-07-01", expiration_date="2026-06-01")],
        )
        assert report.result is ValidationResult.INVALID
        assert report.issues_by_code(ValidationErrorCode.CONSISTENCY_ERROR)

    def test_future_review_date_is_timestamp_error(self) -> None:
        report = DataValidator().validate_compliance(
            "ds-2", [self._valid(review_date="2999-01-01")]
        )
        assert report.issues_by_code(ValidationErrorCode.TIMESTAMP_ERROR)


class TestFundamentalValidation:
    def test_valid_fundamentals(self) -> None:
        report = DataValidator().validate_fundamentals(
            "ds-3",
            [{"symbol": "AAPL", "report_date": "2026-06-30", "revenue": 100.0}],
        )
        assert report.result is ValidationResult.VALID

    def test_missing_report_date_rejected(self) -> None:
        report = DataValidator().validate_fundamentals(
            "ds-3", [{"symbol": "AAPL", "revenue": 100.0}]
        )
        assert report.result is ValidationResult.INVALID
        assert report.issues_by_code(ValidationErrorCode.MISSING_DATA)


class TestReportHelpers:
    def test_raise_for_invalid(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles("ds-1", [{"symbol": "AAPL"}])
        with pytest.raises(DataValidationError):
            raise_for_invalid(report)

    def test_report_summary(self) -> None:
        validator = DataValidator()
        report = validator.validate_candles("ds-1", [_valid_candle(), _valid_candle()])
        summary = report.summary()
        assert "warning" in summary
        assert "ds-1" in summary

    def test_report_timestamp_and_version(self) -> None:
        report = DataValidator().validate_candles("ds-1", [_valid_candle()])
        assert report.timestamp.tzinfo is not None
        assert report.validator_version


def _valid_candle(**overrides) -> dict:
    base = {
        "timestamp": "2026-08-01T13:30:00Z",
        "symbol": "AAPL",
        "timeframe": "1h",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 1000.0,
    }
    base.update(overrides)
    return base
