"""Data Pipeline (AIOS-505).

The pipeline moves data from acquisition to consumption through six stages
(AIOS-505 section 3): acquire, validate, normalize, quality assurance,
storage, and serve. Every stage records metrics for traceability, invalid
datasets stop processing before storage, and historical records are never
overwritten.

The pipeline consumes standardized models only (AIOS-505 section 6). Fetching
is delegated to providers (aios.providers) and storage to Database Layer
repositories (AIOS-606); the pipeline orchestrates both so no module outside
the Data Layer reaches a provider directly.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from aios.data.exceptions import DataPipelineError, DataValidationError
from aios.data.models import Candle
from aios.data.validation import (
    DataValidator,
    ValidationReport,
    ValidationResult,
    raise_for_invalid,
)

_Fetch = Callable[[], Awaitable[Sequence[Mapping | Candle]] | Sequence[Mapping | Candle]]
_Store = Callable[[Sequence[Candle]], int]


class PipelineStage(str, Enum):
    """Data Pipeline stages (AIOS-505 section 3)."""

    ACQUIRE = "acquire"
    VALIDATE = "validate"
    NORMALIZE = "normalize"
    QUALITY_ASSURANCE = "quality_assurance"
    STORAGE = "storage"
    SERVE = "serve"


@dataclass(frozen=True)
class StageMetrics:
    """Timing and outcome for a single pipeline stage (AIOS-505 section 11)."""

    stage: PipelineStage
    started_at: datetime
    duration_seconds: float
    status: str
    record_count: int
    note: str = ""


@dataclass
class PipelineRun:
    """Traceable result of one ingestion run (AIOS-505 section 11).

    Preserves the dataset identifier, the source provider, the validation
    report, per-stage metrics, and record counts for auditability.
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    dataset_id: str = ""
    provider_name: str = ""
    records_ingested: int = 0
    records_normalized: int = 0
    records_stored: int = 0
    validation: ValidationReport | None = None
    validation_result: ValidationResult | None = None
    stages: list[StageMetrics] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_seconds: float = 0.0

    def add_stage(self, stage: StageMetrics) -> None:
        self.stages.append(stage)

    def stage_duration(self, stage: PipelineStage) -> float:
        for metric in self.stages:
            if metric.stage is stage:
                return metric.duration_seconds
        return 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DataPipeline:
    """Orchestrates ingestion of a dataset through all six stages.

    ``fetch`` is provided by a provider (aios.providers) and returns AIOS
    standard models or raw mappings; ``store`` is provided by a Database
    Layer repository and persists validated models. Validation gates storage
    (AIOS-505 section 5): INVALID datasets are rejected, WARNING datasets
    proceed unless ``quarantine_on_warning`` is enabled, and QUARANTINED
    datasets are isolated without storage.
    """

    def __init__(
        self,
        validator: DataValidator,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._validator = validator
        self._logger = logger or logging.getLogger("aios.data.pipeline")

    def validate_candles(
        self, dataset_id: str, data: Sequence[Mapping | Candle]
    ) -> ValidationReport:
        return self._validator.validate_candles(dataset_id, data)

    async def ingest_candles(
        self,
        *,
        dataset_id: str,
        provider_name: str,
        fetch: _Fetch,
        store: _Store,
        normalize: Callable[[Sequence[Candle]], Sequence[Candle]] | None = None,
        quarantine_on_warning: bool = False,
    ) -> PipelineRun:
        """Acquire, validate, normalize, and store a candle dataset."""
        run = PipelineRun(dataset_id=dataset_id, provider_name=provider_name)
        try:
            records = await self._acquire(run, fetch)
            report = self._validate(run, records)
            if not self._decide(run, report, quarantine_on_warning):
                return run
            candles = self._normalize(run, records, normalize)
            self._quality_assurance(run, candles)
            self._store(run, candles, store)
            self._serve(run)
            return run
        except (DataValidationError, DataPipelineError):
            raise
        except Exception as exc:  # noqa: BLE001 - pipeline reports any failure
            self._logger.exception("Pipeline run failed for %s", dataset_id)
            raise DataPipelineError(f"Pipeline failed for dataset {dataset_id!r}: {exc}") from exc

    async def _acquire(self, run: PipelineRun, fetch: _Fetch) -> list[Mapping | Candle]:
        started = time.perf_counter()
        start = _now()
        try:
            result = fetch()
            if isinstance(result, Awaitable):
                result = await result
        except Exception as exc:
            raise DataPipelineError(
                f"Acquire failed for dataset {run.dataset_id!r} from "
                f"provider {run.provider_name!r}: {exc}"
            ) from exc
        records = list(result)
        run.records_ingested = len(records)
        run.add_stage(
            StageMetrics(
                stage=PipelineStage.ACQUIRE,
                started_at=start,
                duration_seconds=time.perf_counter() - started,
                status="ok",
                record_count=run.records_ingested,
                note=f"provider={run.provider_name}",
            )
        )
        return records

    def _validate(self, run: PipelineRun, records: Sequence[Mapping | Candle]) -> ValidationReport:
        started = time.perf_counter()
        start = _now()
        report = self._validator.validate_candles(run.dataset_id, records)
        run.validation = report
        run.validation_result = report.result
        run.add_stage(
            StageMetrics(
                stage=PipelineStage.VALIDATE,
                started_at=start,
                duration_seconds=time.perf_counter() - started,
                status="ok",
                record_count=len(records),
                note=report.summary(),
            )
        )
        return report

    def _decide(
        self, run: PipelineRun, report: ValidationReport, quarantine_on_warning: bool
    ) -> bool:
        if report.result is ValidationResult.QUARANTINED:
            self._logger.warning("Dataset %s quarantined", run.dataset_id)
            run.add_stage(
                StageMetrics(
                    stage=PipelineStage.NORMALIZE,
                    started_at=_now(),
                    duration_seconds=0.0,
                    status="skipped",
                    record_count=0,
                    note="quarantined dataset isolated",
                )
            )
            return False
        if report.result is ValidationResult.INVALID:
            raise_for_invalid(report)
        if report.result is ValidationResult.WARNING and quarantine_on_warning:
            self._logger.warning("Dataset %s quarantined due to warnings", run.dataset_id)
            run.validation_result = ValidationResult.QUARANTINED
            run.add_stage(
                StageMetrics(
                    stage=PipelineStage.NORMALIZE,
                    started_at=_now(),
                    duration_seconds=0.0,
                    status="skipped",
                    record_count=0,
                    note="warnings treated as quarantine by policy",
                )
            )
            return False
        return True

    def _normalize(
        self,
        run: PipelineRun,
        records: Sequence[Mapping | Candle],
        normalize: Callable[[Sequence[Candle]], Sequence[Candle]] | None,
    ) -> list[Candle]:
        started = time.perf_counter()
        start = _now()
        candles = [r for r in records if isinstance(r, Candle)]
        if normalize is not None:
            candles = list(normalize(candles))
        run.records_normalized = len(candles)
        run.add_stage(
            StageMetrics(
                stage=PipelineStage.NORMALIZE,
                started_at=start,
                duration_seconds=time.perf_counter() - started,
                status="ok",
                record_count=run.records_normalized,
            )
        )
        return candles

    def _quality_assurance(self, run: PipelineRun, candles: Sequence[Candle]) -> None:
        started = time.perf_counter()
        start = _now()
        missing = [c for c in candles if c.timestamp.tzinfo is None]
        status = "ok" if not missing else "warning"
        run.add_stage(
            StageMetrics(
                stage=PipelineStage.QUALITY_ASSURANCE,
                started_at=start,
                duration_seconds=time.perf_counter() - started,
                status=status,
                record_count=len(candles),
                note=f"missing_timezone={len(missing)}",
            )
        )

    def _store(self, run: PipelineRun, candles: Sequence[Candle], store: _Store) -> None:
        started = time.perf_counter()
        start = _now()
        try:
            stored = store(candles)
        except Exception as exc:
            raise DataPipelineError(
                f"Storage failed for dataset {run.dataset_id!r}: {exc}"
            ) from exc
        run.records_stored = stored
        run.add_stage(
            StageMetrics(
                stage=PipelineStage.STORAGE,
                started_at=start,
                duration_seconds=time.perf_counter() - started,
                status="ok",
                record_count=stored,
            )
        )

    def _serve(self, run: PipelineRun) -> None:
        started = time.perf_counter()
        start = _now()
        run.add_stage(
            StageMetrics(
                stage=PipelineStage.SERVE,
                started_at=start,
                duration_seconds=time.perf_counter() - started,
                status="ok",
                record_count=run.records_stored,
                note="data ready for consumers",
            )
        )
        run.finished_at = _now()
        run.duration_seconds = (run.finished_at - run.started_at).total_seconds()
