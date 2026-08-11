"""Data validation framework (AIOS-506).

No data shall be processed without successful validation (AIOS-506 section
1). Validation runs at four levels:

    Level 1 - Schema Validation: required fields, names, structure.
    Level 2 - Field Validation: types, ranges, dates, enumerated values.
    Level 3 - Business Rule Validation: logical correctness (AIOS-503
              section 12, AIOS-504 section 10).
    Level 4 - Quality Validation: completeness, accuracy, consistency,
              freshness, reliability.

Levels 1 and 2 are enforced by the standard models (aios.data.models)
constructed through pydantic. This framework classifies construction
failures, applies Level 3 business rules, and runs Level 4 quality checks.
Each validation returns a report with one of the results defined in
AIOS-506 section 6: VALID, WARNING, INVALID, or QUARANTINED.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import ValidationError as PydanticValidationError

from aios.data.exceptions import DataValidationError
from aios.data.models import (
    Candle,
    CompanyFundamentals,
    ShariahCompliance,
    Timeframe,
)
from aios.analysis.news import NewsArticle

VALIDATOR_VERSION = "1.0.0"


class ValidationResult(str, Enum):
    """Validation results (AIOS-506 section 6)."""

    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"
    QUARANTINED = "quarantined"


class ValidationErrorCode(str, Enum):
    """Validation error classifications (AIOS-506 section 7)."""

    MISSING_DATA = "missing_data"
    INVALID_FORMAT = "invalid_format"
    INVALID_VALUE = "invalid_value"
    DUPLICATE_RECORD = "duplicate_record"
    PROVIDER_ERROR = "provider_error"
    TIMESTAMP_ERROR = "timestamp_error"
    CONSISTENCY_ERROR = "consistency_error"


class ValidationIssue:
    """A single validation error with a classification code."""

    __slots__ = ("code", "message", "field")

    def __init__(self, code: ValidationErrorCode, message: str, field: str | None = None) -> None:
        self.code = code
        self.message = message
        self.field = field


class ValidationReport:
    """Result of validating one dataset (AIOS-506 section 11).

    Records the dataset identifier, overall result, detected issues, the
    validation duration, the validation timestamp, and the validator
    version for full auditability.
    """

    def __init__(
        self,
        dataset_id: str,
        result: ValidationResult,
        issues: Sequence[ValidationIssue] = (),
        duration_seconds: float = 0.0,
        timestamp: datetime | None = None,
    ) -> None:
        self.dataset_id = dataset_id
        self.result = result
        self.issues = list(issues)
        self.duration_seconds = duration_seconds
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.validator_version = VALIDATOR_VERSION

    @property
    def is_valid(self) -> bool:
        """Return whether the dataset may continue through the pipeline.

        VALID and WARNING results may continue per policy (AIOS-506 section
        6); INVALID and QUARANTINED datasets stop processing.
        """
        return self.result in (ValidationResult.VALID, ValidationResult.WARNING)

    def issues_by_code(self, code: ValidationErrorCode) -> list[ValidationIssue]:
        """Return the issues classified with ``code``."""
        return [issue for issue in self.issues if issue.code is code]

    def summary(self) -> str:
        """Return a compact human-readable summary of the report."""
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.code.value] = counts.get(issue.code.value, 0) + 1
        details = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
        if not details:
            details = "no issues"
        return f"{self.result.value} ({self.dataset_id}) [{details}]"


def _classify_pydantic_errors(exc: PydanticValidationError) -> list[ValidationIssue]:
    """Classify schema/field failures into AIOS-506 error codes.

    Covers validation Levels 1 and 2 (AIOS-506 sections 4.1 and 4.2).
    """
    issues: list[ValidationIssue] = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error.get("loc", ()))
        error_type = error.get("type", "")
        message = error.get("msg", str(error))
        if "missing" in error_type:
            code = ValidationErrorCode.MISSING_DATA
        elif error_type == "value_error" or "literal_error" in error_type or error_type == "enum":
            code = ValidationErrorCode.INVALID_VALUE
        else:
            code = ValidationErrorCode.INVALID_FORMAT
        issues.append(ValidationIssue(code=code, message=message, field=field))
    return issues


class DataValidator:
    """Four-level validator for AIOS standard data (AIOS-506).

    Levels 1-2 are enforced through pydantic model construction; Level 3
    applies the business rules of AIOS-503 section 12 (candles) and
    AIOS-504 section 10 (compliance); Level 4 applies completeness and
    freshness quality checks. Level 3 business-rule validators can be
    injected without changing the framework (AIOS-506 section 4.3).
    """

    def __init__(self, *, freshness_max_age: timedelta | None = None) -> None:
        self._freshness_max_age = freshness_max_age
        self._candle_business_rules: list[object] = []
        self._compliance_business_rules: list[object] = []

    def add_candle_rule(self, validator: object) -> None:
        """Register an additional Level 3 candle rule.

        The validator must provide ``validate(candle) -> list[ValidationIssue]``.
        """
        self._candle_business_rules.append(validator)

    def add_compliance_rule(self, validator: object) -> None:
        """Register an additional Level 3 compliance rule.

        The validator must provide ``validate(record) -> list[ValidationIssue]``.
        """
        self._compliance_business_rules.append(validator)

    @staticmethod
    def _apply_rule(validator: object, record: object) -> list[ValidationIssue]:
        issues = validator.validate(record)  # type: ignore[attr-defined]
        return list(issues)

    # -- Level 3: business rule validation -------------------------------

    def _candle_business_rules_for(self, candle: Candle) -> list[ValidationIssue]:
        """Enforce the candle validation rules (AIOS-503 section 12)."""
        issues: list[ValidationIssue] = []
        if candle.high < candle.open:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.CONSISTENCY_ERROR,
                    "high must be greater than or equal to open",
                    field="high",
                )
            )
        if candle.high < candle.close:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.CONSISTENCY_ERROR,
                    "high must be greater than or equal to close",
                    field="high",
                )
            )
        if candle.low > candle.open:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.CONSISTENCY_ERROR,
                    "low must be less than or equal to open",
                    field="low",
                )
            )
        if candle.low > candle.close:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.CONSISTENCY_ERROR,
                    "low must be less than or equal to close",
                    field="low",
                )
            )
        if candle.timestamp.tzinfo is None:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.TIMESTAMP_ERROR,
                    "candle timestamp must carry a time zone",
                    field="timestamp",
                )
            )
        for validator in self._candle_business_rules:
            issues.extend(self._apply_rule(validator, candle))
        return issues

    def _compliance_business_rules_for(self, record: ShariahCompliance) -> list[ValidationIssue]:
        """Enforce the compliance record rules (AIOS-504 section 10)."""
        issues: list[ValidationIssue] = []
        if record.expiration_date is not None and record.expiration_date < record.effective_date:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.CONSISTENCY_ERROR,
                    "expiration_date must not precede effective_date",
                    field="expiration_date",
                )
            )
        if record.review_date > datetime.now(timezone.utc).date():
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.TIMESTAMP_ERROR,
                    "review_date must not be in the future",
                    field="review_date",
                )
            )
        for validator in self._compliance_business_rules:
            issues.extend(self._apply_rule(validator, record))
        return issues

    # -- Level 4: quality validation --------------------------------------

    def _freshness_issues(
        self, timestamps: Sequence[datetime], dataset_id: str
    ) -> list[ValidationIssue]:
        if self._freshness_max_age is None:
            return []
        if not timestamps:
            return []
        newest = max(timestamps)
        age = datetime.now(timezone.utc) - newest
        if age > self._freshness_max_age:
            return [
                ValidationIssue(
                    ValidationErrorCode.INVALID_VALUE,
                    f"dataset {dataset_id!r} is stale (age {age} exceeds "
                    f"{self._freshness_max_age})",
                    field="quality.freshness",
                )
            ]
        return []

    @staticmethod
    def _duplicate_issues(candles: Sequence[Candle]) -> list[ValidationIssue]:
        seen: set[tuple[str, Timeframe, datetime]] = set()
        issues: list[ValidationIssue] = []
        for candle in candles:
            key = (candle.symbol, candle.timeframe, candle.timestamp)
            if key in seen:
                issues.append(
                    ValidationIssue(
                        ValidationErrorCode.DUPLICATE_RECORD,
                        f"duplicate candle for {candle.symbol} {candle.timeframe.value} "
                        f"{candle.timestamp}",
                        field="timestamp",
                    )
                )
            seen.add(key)
        return issues

    # -- dataset validators -----------------------------------------------

    def validate_candles(
        self, dataset_id: str, data: Sequence[Mapping | Candle]
    ) -> ValidationReport:
        """Validate a market data dataset (AIOS-503 sections 5 and 12)."""
        started = time.perf_counter()
        structural: list[ValidationIssue] = []
        candles: list[Candle] = []
        for item in data:
            if isinstance(item, Candle):
                candles.append(item)
                continue
            try:
                candles.append(Candle.model_validate(item))
            except PydanticValidationError as exc:
                structural.extend(_classify_pydantic_errors(exc))
        for candle in candles:
            structural.extend(self._candle_business_rules_for(candle))
        quality = self._duplicate_issues(candles)
        quality.extend(self._freshness_issues([c.timestamp for c in candles], dataset_id))
        return self._report(dataset_id, structural, quality, started)

    def validate_compliance(
        self, dataset_id: str, data: Sequence[Mapping | ShariahCompliance]
    ) -> ValidationReport:
        """Validate a Shariah compliance dataset (AIOS-504 section 10)."""
        started = time.perf_counter()
        structural: list[ValidationIssue] = []
        records: list[ShariahCompliance] = []
        for item in data:
            if isinstance(item, ShariahCompliance):
                records.append(item)
                continue
            try:
                records.append(ShariahCompliance.model_validate(item))
            except PydanticValidationError as exc:
                structural.extend(_classify_pydantic_errors(exc))
        for record in records:
            structural.extend(self._compliance_business_rules_for(record))
        return self._report(dataset_id, structural, [], started)

    def validate_fundamentals(
        self, dataset_id: str, data: Sequence[Mapping | CompanyFundamentals]
    ) -> ValidationReport:
        """Validate a company fundamentals dataset (AIOS-502 section 6)."""
        started = time.perf_counter()
        structural: list[ValidationIssue] = []
        for item in data:
            if isinstance(item, CompanyFundamentals):
                continue
            try:
                CompanyFundamentals.model_validate(item)
            except PydanticValidationError as exc:
                structural.extend(_classify_pydantic_errors(exc))
        return self._report(dataset_id, structural, [], started)

    def validate_news(
        self, dataset_id: str, data: Sequence[Mapping | NewsArticle]
    ) -> ValidationReport:
        """Validate a news dataset (Phase 9.1).

        Validates news articles for required fields, timestamp validity,
        and structural integrity.
        """
        started = time.perf_counter()
        structural: list[ValidationIssue] = []
        articles: list[NewsArticle] = []
        for item in data:
            if isinstance(item, NewsArticle):
                articles.append(item)
                continue
            try:
                articles.append(NewsArticle.model_validate(item))
            except PydanticValidationError as exc:
                structural.extend(_classify_pydantic_errors(exc))
        for article in articles:
            structural.extend(self._news_business_rules_for(article))
        quality = self._news_quality_issues(articles, dataset_id)
        return self._report(dataset_id, structural, quality, started)

    def _news_business_rules_for(self, article: NewsArticle) -> list[ValidationIssue]:
        """Enforce news article business rules (Phase 9.1)."""
        issues: list[ValidationIssue] = []
        if article.published_at > datetime.now(timezone.utc):
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.TIMESTAMP_ERROR,
                    "published_at must not be in the future",
                    field="published_at",
                )
            )
        if article.retrieved_at < article.published_at:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.CONSISTENCY_ERROR,
                    "retrieved_at must not be before published_at",
                    field="retrieved_at",
                )
            )
        if not article.headline or not article.headline.strip():
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.MISSING_DATA,
                    "headline must not be empty",
                    field="headline",
                )
            )
        if not article.symbols:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.MISSING_DATA,
                    "at least one symbol must be provided",
                    field="symbols",
                )
            )
        if article.summary and len(article.summary) > 5000:
            issues.append(
                ValidationIssue(
                    ValidationErrorCode.INVALID_VALUE,
                    "summary exceeds maximum length of 5000 characters",
                    field="summary",
                )
            )
        return issues

    def _news_quality_issues(
        self, articles: list[NewsArticle], dataset_id: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not articles:
            return issues
        # Check for duplicate articles (same provider + article_id)
        seen: set[tuple[str, str]] = set()
        for article in articles:
            key = (article.provider, article.article_id)
            if key in seen:
                issues.append(
                    ValidationIssue(
                        ValidationErrorCode.DUPLICATE_RECORD,
                        f"duplicate article {article.article_id} from provider {article.provider}",
                        field="article_id",
                    )
                )
            seen.add(key)
        # Freshness check
        if self._freshness_max_age is not None:
            newest = max(article.published_at for article in articles)
            age = datetime.now(timezone.utc) - newest
            if age > self._freshness_max_age:
                issues.append(
                    ValidationIssue(
                        ValidationErrorCode.INVALID_VALUE,
                        f"dataset {dataset_id!r} is stale (age {age} exceeds "
                        f"{self._freshness_max_age})",
                        field="quality.freshness",
                    )
                )
        return issues

    def _report(
        self,
        dataset_id: str,
        structural: Sequence[ValidationIssue],
        quality: Sequence[ValidationIssue],
        started: float,
    ) -> ValidationReport:
        duration = time.perf_counter() - started
        issues = list(structural) + list(quality)
        if structural:
            result = ValidationResult.INVALID
        elif quality:
            result = ValidationResult.WARNING
        else:
            result = ValidationResult.VALID
        return ValidationReport(
            dataset_id=dataset_id,
            result=result,
            issues=issues,
            duration_seconds=duration,
        )


def raise_for_invalid(report: ValidationReport) -> None:
    """Raise :class:`DataValidationError` when ``report`` is not valid.

    Implements AIOS-505 section 5: invalid datasets shall not continue
    through the pipeline.
    """
    if not report.is_valid:
        raise DataValidationError(
            f"Dataset {report.dataset_id!r} failed validation: {report.summary()}"
        )
