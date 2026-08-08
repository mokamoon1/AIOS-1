"""Data infrastructure integration tests (ADR-0001, ADR-0006).

End-to-end flows on the SQLite test database: provider -> standardized
model -> Data Pipeline -> repository storage, validation gating, and Event
Bus save-before-publish persistence (ADR-0005 section 5.5).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios.data.models import (
    AssetType,
    Candle,
    ComplianceStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.data.pipeline import DataPipeline
from aios.data.services import DataService
from aios.data.validation import DataValidator
from aios.database.repositories import (
    CompanyRepository,
    EventLogRepository,
    MarketRepository,
    ShariahRepository,
)
from aios.events.bus import InMemoryEventBus
from aios.events.event import Event

pytestmark = pytest.mark.integration


class _MarketProvider:
    """Stub provider returning standardized models (AIOS-607)."""

    name = "test-market"

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    async def fetch(self) -> list[Candle]:
        return self._candles


def _candle(day: int) -> Candle:
    return Candle(
        timestamp=datetime(2026, 8, day, 13, 30, tzinfo=timezone.utc),
        symbol="AAPL",
        timeframe=Timeframe.ONE_HOUR,
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000.0,
    )


class TestPipelineEndToEnd:
    async def test_provider_to_pipeline_to_repository(self, session_factory) -> None:
        market = MarketRepository(session_factory)
        pipeline = DataPipeline(DataValidator())
        service = DataService(pipeline, market_repository=market)

        provider = _MarketProvider([_candle(1), _candle(2)])
        run = await service.ingest_candles(
            dataset_id="integration-1",
            provider_name=provider.name,
            fetch=provider.fetch,
            store=lambda records: market.add_candles(list(records), provider.name),
        )

        assert run.records_stored == 2
        candles = market.get_candles("AAPL", Timeframe.ONE_HOUR)
        assert len(candles) == 2
        assert candles[0].timestamp.tzinfo is not None

    async def test_invalid_data_is_not_stored(self, session_factory) -> None:
        market = MarketRepository(session_factory)
        pipeline = DataPipeline(DataValidator())
        service = DataService(pipeline, market_repository=market)

        bad = {
            "timestamp": "2026-08-01T13:30:00Z",
            "symbol": "AAPL",
            "timeframe": "1h",
            "open": 100.0,
            "high": 90.0,  # high < open -> invalid
            "low": 99.0,
            "close": 104.0,
            "volume": 1000.0,
        }

        from aios.data.exceptions import DataValidationError

        with pytest.raises(DataValidationError):
            await service.ingest_candles(
                dataset_id="integration-bad",
                provider_name="test-market",
                fetch=lambda: [bad],
                store=lambda records: market.add_candles(list(records), "test-market"),
            )
        assert market.get_candles("AAPL", Timeframe.ONE_HOUR) == []

    async def test_duplicate_ingestion_is_immutable(self, session_factory) -> None:
        market = MarketRepository(session_factory)
        pipeline = DataPipeline(DataValidator())
        service = DataService(pipeline, market_repository=market)

        provider = _MarketProvider([_candle(1)])
        for _ in range(2):
            await service.ingest_candles(
                dataset_id="integration-dedup",
                provider_name=provider.name,
                fetch=provider.fetch,
                store=lambda records: market.add_candles(list(records), provider.name),
            )
        assert len(market.get_candles("AAPL", Timeframe.ONE_HOUR)) == 1


class TestRepositoryIntegration:
    def test_shariah_and_fundamentals_persist(self, session_factory) -> None:
        shariah = ShariahRepository(session_factory)
        company = CompanyRepository(session_factory)

        shariah.add_records(
            [
                ShariahCompliance(
                    symbol="AAPL",
                    company_name="Apple Inc.",
                    exchange="NASDAQ",
                    country="US",
                    asset_type=AssetType.EQUITY,
                    compliance_status=ComplianceStatus.COMPLIANT,
                    provider="test",
                    review_date="2026-07-01",
                    effective_date="2026-07-01",
                    screening_methodology="test",
                    screening_date="2026-07-01",
                )
            ]
        )
        from aios.data.models import CompanyFundamentals

        company.add_fundamentals(
            [CompanyFundamentals(symbol="AAPL", report_date="2026-06-30", revenue=100.0)]
        )

        assert shariah.get_compliance_status("AAPL").compliance_status is ComplianceStatus.COMPLIANT
        assert company.get_fundamentals("AAPL").revenue == 100.0


class TestEventBusPersistence:
    async def test_save_before_publish(self, session_factory) -> None:
        repository = EventLogRepository(session_factory)
        bus = InMemoryEventBus(repository=repository)
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("DATA_UPDATED", handler)
        event = Event(source="test", event_type="DATA_UPDATED", payload={"n": 1})
        await bus.publish(event)

        restored = await repository.get(event.event_id)
        assert restored is not None
        assert restored.event_id == event.event_id
        assert restored.event_type == "DATA_UPDATED"
        assert len(received) == 1
