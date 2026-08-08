"""Performance measurement tests (AIOS-705).

AIOS-705 defines the metrics that must be measured (execution time, response
time, throughput, failure rate; sections 4 and 11) and requires measurements
to be reproducible (section 4) and retained for trend analysis (section 12).
Acceptance thresholds are explicitly project-defined and "may evolve"
(section 13): none are fixed in the approved documents, so these tests
measure and report only, and never assert an invented threshold.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import aios.core.engine as core_module
import aios.database.models  # noqa: F401  (register ORM models on Base.metadata)
from aios.config import Environment
from aios.core import CoreEngine
from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.database.base import Base
from aios.database.repositories import CompanyRepository, MarketRepository, ShariahRepository
from aios.engines.messages import EngineInput
from aios.engines.types import EngineType
from aios.monitoring import HealthMonitor

pytestmark = pytest.mark.performance

_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


def _sqlite_engine():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


async def _boot_seeded(monkeypatch: pytest.MonkeyPatch) -> CoreEngine:
    monkeypatch.setattr(core_module, "create_db_engine", lambda url, **kwargs: _sqlite_engine())
    import logging

    monkeypatch.setattr(core_module, "setup_logging", lambda settings: logging.getLogger("aios"))
    monkeypatch.setattr(
        core_module, "setup_audit_handler", lambda logger: logging.getLogger("aios.audit")
    )
    core = CoreEngine(environment=Environment.TESTING)
    await core.start()
    session_factory = core.session_factory
    candles = []
    for index in range(250):
        close = 10.0 + index * 0.1
        candles.append(
            Candle(
                timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc) + timedelta(days=index),
                symbol="AAPL",
                timeframe=Timeframe.ONE_DAY,
                open=close,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1000.0,
            )
        )
    MarketRepository(session_factory).add_candles(candles, provider="test")
    ShariahRepository(session_factory).add_records(
        [
            ShariahCompliance(
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
        ]
    )
    CompanyRepository(session_factory).add_fundamentals(
        [
            CompanyFundamentals(
                symbol="AAPL",
                sector="Technology",
                revenue=1000.0,
                net_income=150.0,
                assets=2000.0,
                liabilities=800.0,
                equity=1200.0,
                report_date=date(2026, 6, 30),
            )
        ]
    )
    return core


def _measurement_report(metrics: list[dict]) -> dict:
    """Build the documented measurement report from engine metrics."""
    snapshot = HealthMonitor().snapshot(
        {"state": "ready", "components": {"database": True}}, engine_metrics=metrics
    )
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engines": snapshot.performance,
        "metrics_measured": [
            "execution_count",
            "failure_count",
            "total_duration_seconds",
            "average_duration_seconds",
            "throughput_per_second",
        ],
    }


class TestEnginePerformanceMeasurement:
    async def test_execution_duration_is_measured_and_recorded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_seeded(monkeypatch)
        try:
            market = core.engine_manager.get_by_type(EngineType.MARKET)[0]
            await core.engine_manager.execute(
                market.engine_id, EngineInput(request_id="perf-1", payload={"symbol": "AAPL"})
            )
            metrics = market.metrics()
            assert metrics["execution_count"] == 1
            assert metrics["failure_count"] == 0
            assert metrics["failure_rate"] == 0.0
            assert metrics["total_duration_seconds"] >= 0
            assert metrics["average_duration_seconds"] >= 0
            assert metrics["average_duration_seconds"] == pytest.approx(
                metrics["total_duration_seconds"]
            )
        finally:
            await core.shutdown()

    async def test_concurrent_analyses_complete_with_measured_throughput(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_seeded(monkeypatch)
        try:
            market = core.engine_manager.get_by_type(EngineType.MARKET)[0]
            request_count = 10

            async def run(index: int) -> None:
                await core.engine_manager.execute(
                    market.engine_id,
                    EngineInput(request_id=f"perf-{index}", payload={"symbol": "AAPL"}),
                )

            started = datetime.now(timezone.utc)
            await asyncio.gather(*(run(index) for index in range(request_count)))
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()

            metrics = market.metrics()
            assert metrics["execution_count"] == request_count
            assert metrics["failure_count"] == 0
            assert elapsed >= 0
            throughput = request_count / elapsed if elapsed > 0 else 0.0
            assert throughput > 0
            assert metrics["average_duration_seconds"] >= 0
        finally:
            await core.shutdown()

    def test_measurement_report_contains_no_invented_thresholds(self) -> None:
        report = _measurement_report(
            [
                {
                    "engine_type": "market",
                    "execution_count": 3,
                    "failure_count": 0,
                    "total_duration_seconds": 1.5,
                }
            ]
        )
        assert report["engines"]["execution_count"] == 3
        assert report["engines"]["total_duration_seconds"] == pytest.approx(1.5)
        for implied_threshold in (
            "max_response_time",
            "min_throughput",
            "max_latency",
            "target_response",
        ):
            assert implied_threshold not in json.dumps(report)

    async def test_measurements_are_reproducible_in_structure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        core = await _boot_seeded(monkeypatch)
        try:
            market = core.engine_manager.get_by_type(EngineType.MARKET)[0]
            for index in range(2):
                await core.engine_manager.execute(
                    market.engine_id,
                    EngineInput(request_id=f"perf-rep-{index}", payload={"symbol": "AAPL"}),
                )
            metrics = market.metrics()
            assert metrics["execution_count"] == 2
            assert metrics["failure_count"] == 0
            assert metrics["total_duration_seconds"] >= 0
            assert len(metrics["confidence_distribution"]) == 2
            assert all(
                0.0 <= confidence <= 1.0 for confidence in metrics["confidence_distribution"]
            )
        finally:
            await core.shutdown()


class TestPerformanceReportArtifact:
    async def test_report_retained_for_trend_analysis(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AIOS-705 section 12: historical metrics are retained for trend analysis."""
        core = await _boot_seeded(monkeypatch)
        try:
            market = core.engine_manager.get_by_type(EngineType.MARKET)[0]
            await core.engine_manager.execute(
                market.engine_id, EngineInput(request_id="perf-report", payload={"symbol": "AAPL"})
            )
            report = _measurement_report([market.metrics()])
            _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            target = _REPORTS_DIR / "performance_measurements.json"
            target.write_text(json.dumps(report, indent=2), encoding="utf-8")
            assert target.exists()
            assert target.stat().st_size > 0
            assert json.loads(target.read_text(encoding="utf-8"))["engines"]["execution_count"] == 1
        finally:
            await core.shutdown()
