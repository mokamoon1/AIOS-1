"""Data Pipeline tests (AIOS-505)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios.data.exceptions import DataPipelineError, DataValidationError
from aios.data.models import Candle
from aios.data.pipeline import DataPipeline, PipelineStage
from aios.data.validation import DataValidator, ValidationResult

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _candle(offset: int = 0, **overrides) -> Candle:
    base = {
        "timestamp": _now(),
        "symbol": "AAPL",
        "timeframe": "1h",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 1000.0,
    }
    if offset:
        base["timestamp"] = _now().replace(second=(base["timestamp"].second + offset) % 60)
    base.update(overrides)
    return Candle.model_validate(base)


class TestPipelineHappyPath:
    async def test_full_run_executes_all_stages(self) -> None:
        candles = [_candle(0), _candle(1)]
        stored: list[Candle] = []

        def store(records) -> int:
            stored.extend(records)
            return len(records)

        pipeline = DataPipeline(DataValidator())
        run = await pipeline.ingest_candles(
            dataset_id="ds-1",
            provider_name="test-provider",
            fetch=lambda: candles,
            store=store,
        )

        assert run.records_ingested == 2
        assert run.records_stored == 2
        assert run.validation is not None
        assert run.validation.result is ValidationResult.VALID
        assert len(stored) == 2
        assert {metric.stage for metric in run.stages} == {
            PipelineStage.ACQUIRE,
            PipelineStage.VALIDATE,
            PipelineStage.NORMALIZE,
            PipelineStage.QUALITY_ASSURANCE,
            PipelineStage.STORAGE,
            PipelineStage.SERVE,
        }
        assert run.finished_at is not None
        assert run.duration_seconds >= 0
        assert run.provider_name == "test-provider"

    async def test_async_fetch_supported(self) -> None:
        async def fetch():
            return [_candle()]

        pipeline = DataPipeline(DataValidator())
        run = await pipeline.ingest_candles(
            dataset_id="ds-1",
            provider_name="p",
            fetch=fetch,
            store=lambda records: len(records),
        )
        assert run.records_ingested == 1

    async def test_normalize_hook_applied(self) -> None:
        def normalize(candles):
            return candles[:1]

        pipeline = DataPipeline(DataValidator())
        run = await pipeline.ingest_candles(
            dataset_id="ds-1",
            provider_name="p",
            fetch=lambda: [_candle(0), _candle(1)],
            store=lambda records: len(records),
            normalize=normalize,
        )
        assert run.records_normalized == 1


class TestPipelineFailureHandling:
    async def test_invalid_data_stops_pipeline(self) -> None:
        pipeline = DataPipeline(DataValidator())
        bad = _candle()
        bad_dict = {
            "timestamp": bad.timestamp,
            "symbol": bad.symbol,
            "timeframe": "1h",
            "open": bad.open,
            "high": 90.0,  # high < open -> invalid
            "low": bad.low,
            "close": bad.close,
            "volume": bad.volume,
        }
        with pytest.raises(DataValidationError):
            await pipeline.ingest_candles(
                dataset_id="ds-1",
                provider_name="p",
                fetch=lambda: [bad_dict],
                store=lambda records: len(records),
            )

    async def test_acquire_failure_raises_pipeline_error(self) -> None:
        def fetch():
            raise RuntimeError("provider unreachable")

        pipeline = DataPipeline(DataValidator())
        with pytest.raises(DataPipelineError):
            await pipeline.ingest_candles(
                dataset_id="ds-1",
                provider_name="p",
                fetch=fetch,
                store=lambda records: len(records),
            )

    async def test_storage_failure_raises_pipeline_error(self) -> None:
        def store(records):
            raise RuntimeError("db down")

        pipeline = DataPipeline(DataValidator())
        with pytest.raises(DataPipelineError):
            await pipeline.ingest_candles(
                dataset_id="ds-1",
                provider_name="p",
                fetch=lambda: [_candle()],
                store=store,
            )

    async def test_warnings_proceed_by_default(self) -> None:
        pipeline = DataPipeline(DataValidator())
        run = await pipeline.ingest_candles(
            dataset_id="ds-1",
            provider_name="p",
            fetch=lambda: [_candle(), _candle()],  # duplicate -> warning
            store=lambda records: len(records),
        )
        assert run.validation_result is ValidationResult.WARNING
        assert run.records_stored == 2

    async def test_quarantine_on_warning_skips_storage(self) -> None:
        stored: list = []

        pipeline = DataPipeline(DataValidator())
        run = await pipeline.ingest_candles(
            dataset_id="ds-1",
            provider_name="p",
            fetch=lambda: [_candle(), _candle()],  # duplicate -> warning
            store=lambda records: stored.extend(records) or len(records),
            quarantine_on_warning=True,
        )
        assert run.validation_result is ValidationResult.QUARANTINED
        assert stored == []

    async def test_empty_dataset_is_valid(self) -> None:
        pipeline = DataPipeline(DataValidator())
        run = await pipeline.ingest_candles(
            dataset_id="ds-1",
            provider_name="p",
            fetch=lambda: [],
            store=lambda records: len(records),
        )
        assert run.records_ingested == 0
        assert run.validation_result is ValidationResult.VALID

    async def test_validate_candles_delegates(self) -> None:
        pipeline = DataPipeline(DataValidator())
        report = pipeline.validate_candles("ds-1", [_candle()])
        assert report.result is ValidationResult.VALID

    async def test_run_trace_fields(self) -> None:
        pipeline = DataPipeline(DataValidator())
        run = await pipeline.ingest_candles(
            dataset_id="ds-1",
            provider_name="p",
            fetch=lambda: [_candle()],
            store=lambda records: len(records),
        )
        assert run.run_id
        assert run.started_at <= run.finished_at
        assert run.stage_duration(PipelineStage.VALIDATE) >= 0
