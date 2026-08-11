"""Phase 9.6 benchmark tests (P0-6).

The Phase 9.6 audit required P0-6 (performance benchmarks) to be measured
instead of absent. These tests measure the two documented critical latencies
end-to-end through real code paths and assert the thresholds recorded in the
audit baseline:

* ``ingestion_latency`` — Data Pipeline candle ingestion (acquire -> validate
  -> normalize -> quality assurance -> store -> serve); p95 < 100 ms.
* ``decision_latency``   — Decision Engine full execution lifecycle (load data
  -> validate -> analyze -> validate output -> publish) producing a
  recommendation from validated engine inputs; p95 < 500 ms.

Latencies are measured with ``time.perf_counter`` and retained in
``tests/reports/phase9_6_benchmarks.json`` for trend analysis (AIOS-705
sections 4 and 12). No measured value is hard-coded: the assertions compare
real measurements against the documented thresholds.
"""

from __future__ import annotations

import asyncio
import json
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.data.pipeline import DataPipeline
from aios.data.validation import DataValidator
from aios.engines import Engine
from aios.engines.messages import EngineInput
from aios.engines.roster import DecisionEngine
from aios.engines.types import EngineType
from aios.errors import DataError

pytestmark = pytest.mark.performance

_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"

# Documented Phase 9.6 audit thresholds (p95).
_INGESTION_P95_THRESHOLD_MS = 100.0
_DECISION_P95_THRESHOLD_MS = 500.0


def _candle_model(index: int) -> Candle:
    close = 10.0 + index * 0.5 + (index % 3) * 0.25
    return Candle(
        timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc) + timedelta(days=index),
        symbol="AAPL",
        timeframe=Timeframe.ONE_DAY,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1000.0,
    )


def _compliance() -> ShariahCompliance:
    return ShariahCompliance(
        symbol="AAPL",
        company_name="Apple",
        exchange="NASDAQ",
        country="US",
        asset_type=AssetType.EQUITY,
        compliance_status=ComplianceStatus.COMPLIANT,
        provider="test",
        review_date=date(2026, 1, 1),
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31),
        screening_methodology="test",
        screening_date=date(2026, 1, 1),
    )


def _fundamentals() -> CompanyFundamentals:
    return CompanyFundamentals(
        symbol="AAPL",
        sector="Technology",
        industry="Hardware",
        revenue=1000.0,
        net_income=150.0,
        eps=1.5,
        assets=2000.0,
        liabilities=800.0,
        cash_flow=250.0,
        equity=1200.0,
        report_date=date(2026, 6, 30),
    )


def _prior_outputs() -> dict:
    return {
        "market": {"market_bias": "bullish", "market_score": 0.8},
        "technical": {"structure": {"direction": "uptrend", "strength": 0.7}},
        "fundamental": {"symbol": "AAPL", "available": ["revenue"]},
        "risk": {"approval_status": "approved", "risk_level": "acceptable", "risk_score": 0.4},
    }


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[index]


class TestIngestionLatencyBenchmark:
    async def test_candle_ingestion_p95_under_100ms(self) -> None:
        """Full pipeline ingestion of 100 candles must stay under 100 ms p95."""
        pipeline = DataPipeline(DataValidator())
        dataset_size = 100
        records = [_candle_model(i) for i in range(dataset_size)]
        stored: list[Candle] = []

        def fetch() -> list[Candle]:
            return records

        def store(candles: list[Candle]) -> int:
            stored.extend(candles)
            return len(candles)

        # Warm-up run (validates code path, excluded from measurement).
        await pipeline.ingest_candles(
            dataset_id="bench-warmup",
            provider_name="test",
            fetch=fetch,
            store=store,
        )

        durations_ms: list[float] = []
        for run_index in range(3):
            stored.clear()
            started = _perf_ms()
            run = await pipeline.ingest_candles(
                dataset_id=f"bench-{run_index}",
                provider_name="test",
                fetch=fetch,
                store=store,
            )
            durations_ms.append(_perf_ms() - started)
            assert run.records_ingested == dataset_size
            assert run.records_stored == dataset_size
            assert len(stored) == dataset_size

        measured_p95 = _p95(durations_ms)
        assert measured_p95 < _INGESTION_P95_THRESHOLD_MS, (
            f"ingestion p95 {measured_p95:.1f}ms exceeded threshold "
            f"{_INGESTION_P95_THRESHOLD_MS:g}ms"
        )

    async def test_ingestion_per_candle_latency_recorded(self) -> None:
        """Per-candle latency is measured and reported, not guessed."""
        pipeline = DataPipeline(DataValidator())
        dataset_size = 50
        records = [_candle_model(i) for i in range(dataset_size)]

        async def fetch() -> list[Candle]:
            return records

        def store(candles: list[Candle]) -> int:
            return len(candles)

        started = _perf_ms()
        run = await pipeline.ingest_candles(
            dataset_id="bench-record",
            provider_name="test",
            fetch=fetch,
            store=store,
        )
        total_ms = _perf_ms() - started
        per_candle = total_ms / dataset_size if dataset_size else 0.0
        assert run.duration_seconds >= 0
        assert per_candle >= 0
        assert per_candle < _INGESTION_P95_THRESHOLD_MS


class TestDecisionLatencyBenchmark:
    async def test_decision_p95_under_500ms(self) -> None:
        """Decision Engine full lifecycle must stay under 500 ms p95."""
        data_access = _DecisionDataAccess(
            candles=[_candle_model(i) for i in range(40)],
            fundamentals=_fundamentals(),
        )
        engine = DecisionEngine(data_access=data_access)
        engine.initialize()

        input_template = EngineInput(
            request_id="bench-decision",
            payload={"symbol": "AAPL", "engine_outputs": _prior_outputs()},
        )

        # Warm-up run.
        await engine.execute(input_template.model_copy(update={"request_id": "warmup"}))

        durations_ms: list[float] = []
        for run_index in range(5):
            started = _perf_ms()
            result = await engine.execute(
                input_template.model_copy(update={"request_id": f"bench-{run_index}"})
            )
            durations_ms.append(_perf_ms() - started)
            assert result.engine_type is EngineType.DECISION
            assert result.processing_duration >= 0
            output = result.output
            assert "decision" in output
            assert output["persisted"] is True

        measured_p95 = _p95(durations_ms)
        assert measured_p95 < _DECISION_P95_THRESHOLD_MS, (
            f"decision p95 {measured_p95:.1f}ms exceeded threshold "
            f"{_DECISION_P95_THRESHOLD_MS:g}ms"
        )

    async def test_decision_latency_measured_from_engine_metrics(self) -> None:
        """Engine metrics reflect real measured execution durations."""
        data_access = _DecisionDataAccess(
            candles=[_candle_model(i) for i in range(40)],
            fundamentals=_fundamentals(),
        )
        engine = DecisionEngine(data_access=data_access)
        engine.initialize()
        for run_index in range(3):
            await engine.execute(
                EngineInput(
                    request_id=f"metric-{run_index}",
                    payload={"symbol": "AAPL", "engine_outputs": _prior_outputs()},
                )
            )
        metrics = engine.metrics()
        assert metrics["execution_count"] == 3
        assert metrics["failure_count"] == 0
        assert metrics["total_duration_seconds"] > 0
        assert metrics["average_duration_seconds"] > 0
        assert metrics["average_duration_seconds"] * 1000 < _DECISION_P95_THRESHOLD_MS


class TestBenchmarkReportArtifact:
    async def test_benchmark_report_retained_for_trend_analysis(self) -> None:
        """Measurements are retained for trend analysis (AIOS-705 section 12)."""
        pipeline = DataPipeline(DataValidator())
        records = [_candle_model(i) for i in range(20)]

        async def fetch() -> list[Candle]:
            return records

        def store(candles: list[Candle]) -> int:
            return len(candles)

        started = _perf_ms()
        ingestion_run = await pipeline.ingest_candles(
            dataset_id="bench-report", provider_name="test", fetch=fetch, store=store
        )
        ingestion_ms = _perf_ms() - started

        data_access = _DecisionDataAccess(
            candles=[_candle_model(i) for i in range(40)],
            fundamentals=_fundamentals(),
        )
        engine = DecisionEngine(data_access=data_access)
        engine.initialize()
        started = _perf_ms()
        decision_result = await engine.execute(
            EngineInput(
                request_id="report-decision",
                payload={"symbol": "AAPL", "engine_outputs": _prior_outputs()},
            )
        )
        decision_ms = _perf_ms() - started

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "9.6",
            "ingestion": {
                "records": 20,
                "p95_threshold_ms": _INGESTION_P95_THRESHOLD_MS,
                "measured_ms": round(ingestion_ms, 3),
                "pass": ingestion_ms < _INGESTION_P95_THRESHOLD_MS,
            },
            "decision": {
                "processing_duration_ms": round(decision_result.processing_duration * 1000, 3),
                "p95_threshold_ms": _DECISION_P95_THRESHOLD_MS,
                "measured_ms": round(decision_ms, 3),
                "pass": decision_ms < _DECISION_P95_THRESHOLD_MS,
            },
        }

        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        target = _REPORTS_DIR / "phase9_6_benchmarks.json"
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        assert target.exists()
        assert target.stat().st_size > 0
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["phase"] == "9.6"
        assert loaded["ingestion"]["pass"] is True
        assert loaded["decision"]["pass"] is True


def _perf_ms() -> float:
    import time

    return time.perf_counter() * 1000.0


class _DecisionDataAccess:
    """In-memory data facade for the Decision Engine (benchmark only)."""

    def __init__(
        self,
        *,
        candles: list[Candle] | None = None,
        fundamentals: CompanyFundamentals | None = None,
    ) -> None:
        self._candles = candles or []
        self._fundamentals = fundamentals
        self._stored: list = []

    def get_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000):
        return self._candles

    def get_fundamentals(self, symbol, *, report_date=None):
        if self._fundamentals is None:
            raise DataError("no fundamentals")
        return self._fundamentals

    def get_compliance_status(self, symbol, *, as_of=None):
        return _compliance()

    def list_positions(self, *, status=None):
        return []

    def store_decisions(self, decisions: list) -> int:
        self._stored.extend(decisions)
        return len(decisions)
