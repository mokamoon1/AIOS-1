"""Tests for DataProviderAdapter interface and result types (AIOS-505, AIOS-607)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.providers.adapter import (
    BatchIngestionResult,
    DataProviderAdapter,
    FundamentalDataAdapter,
    IngestionResult,
    IngestionResultType,
    MarketDataAdapter,
    ShariahDataAdapter,
)


class _FakeMarketAdapter:
    """Fake market adapter for testing."""

    name = "fake-market-adapter"
    provider_name = "fake-market"

    async def fetch_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000):
        return [
            Candle(
                timestamp=datetime(2026, 8, 1, 13, 30, tzinfo=timezone.utc),
                symbol=symbol,
                timeframe=timeframe,
                open=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                volume=1000.0,
            )
        ]

    async def fetch_security(self, symbol, exchange):
        return Security(
            symbol=symbol,
            exchange=exchange,
            asset_type=AssetType.EQUITY,
            currency="USD",
            trading_session="regular",
            timezone="America/New_York",
            market_status="open",
        )

    async def fetch_compliance(self, symbol):
        return ShariahCompliance(
            symbol=symbol,
            company_name="Test",
            exchange="NASDAQ",
            country="US",
            asset_type=AssetType.EQUITY,
            compliance_status=ComplianceStatus.COMPLIANT,
            provider="fake",
            review_date=date(2026, 7, 1),
            effective_date=date(2026, 7, 1),
            screening_methodology="test",
            screening_date=date(2026, 7, 1),
        )

    async def fetch_compliance_history(self, symbol, *, since=None):
        return [
            ShariahCompliance(
                symbol=symbol,
                company_name="Test",
                exchange="NASDAQ",
                country="US",
                asset_type=AssetType.EQUITY,
                compliance_status=ComplianceStatus.COMPLIANT,
                provider="fake",
                review_date=date(2026, 7, 1),
                effective_date=date(2026, 7, 1),
                screening_methodology="test",
                screening_date=date(2026, 7, 1),
            )
        ]

    async def fetch_fundamentals(self, symbol):
        return CompanyFundamentals(
            symbol=symbol,
            sector="Technology",
            industry="Software",
            revenue=1000.0,
            net_income=200.0,
            eps=2.5,
            report_date=date(2026, 6, 30),
        )


class _FakeShariahAdapter:
    """Fake Shariah adapter for testing."""

    name = "fake-shariah-adapter"
    provider_name = "fake-shariah"

    async def fetch_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000):
        return []

    async def fetch_security(self, symbol, exchange):
        raise NotImplementedError

    async def fetch_compliance(self, symbol):
        return ShariahCompliance(
            symbol=symbol,
            company_name="Test",
            exchange="NASDAQ",
            country="US",
            asset_type=AssetType.EQUITY,
            compliance_status=ComplianceStatus.COMPLIANT,
            provider="fake-shariah",
            review_date=date(2026, 7, 1),
            effective_date=date(2026, 7, 1),
            screening_methodology="test",
            screening_date=date(2026, 7, 1),
        )

    async def fetch_compliance_history(self, symbol, *, since=None):
        return []

    async def fetch_fundamentals(self, symbol):
        raise NotImplementedError


class _FakeFundamentalAdapter:
    """Fake fundamental adapter for testing."""

    name = "fake-fundamental-adapter"
    provider_name = "fake-fundamental"

    async def fetch_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000):
        return []

    async def fetch_security(self, symbol, exchange):
        raise NotImplementedError

    async def fetch_compliance(self, symbol):
        raise NotImplementedError

    async def fetch_compliance_history(self, symbol, *, since=None):
        return []

    async def fetch_fundamentals(self, symbol):
        return CompanyFundamentals(
            symbol=symbol,
            sector="Technology",
            industry="Software",
            revenue=1000.0,
            net_income=200.0,
            eps=2.5,
            report_date=date(2026, 6, 30),
        )


async def test_adapter_protocol_market() -> None:
    """Test MarketDataAdapter protocol conformance."""
    adapter = _FakeMarketAdapter()
    assert isinstance(adapter, MarketDataAdapter)
    assert isinstance(adapter, DataProviderAdapter)
    assert adapter.name == "fake-market-adapter"
    assert adapter.provider_name == "fake-market"


async def test_adapter_protocol_shariah() -> None:
    """Test ShariahDataAdapter protocol conformance."""
    adapter = _FakeShariahAdapter()
    assert isinstance(adapter, ShariahDataAdapter)
    assert isinstance(adapter, DataProviderAdapter)
    assert adapter.name == "fake-shariah-adapter"


async def test_adapter_protocol_fundamental() -> None:
    """Test FundamentalDataAdapter protocol conformance."""
    adapter = _FakeFundamentalAdapter()
    assert isinstance(adapter, FundamentalDataAdapter)
    assert isinstance(adapter, DataProviderAdapter)
    assert adapter.name == "fake-fundamental-adapter"


async def test_ingestion_result_creation() -> None:
    """Test IngestionResult dataclass creation."""
    result = IngestionResult(
        dataset_id="test-123",
        provider_name="test-provider",
        result_type=IngestionResultType.SUCCESS,
        records_fetched=10,
        records_validated=10,
        records_stored=10,
    )
    assert result.dataset_id == "test-123"
    assert result.provider_name == "test-provider"
    assert result.result_type == IngestionResultType.SUCCESS
    assert result.records_fetched == 10
    assert result.records_validated == 10
    assert result.records_stored == 10
    assert result.error_message is None
    assert result.validation_report is None


async def test_ingestion_result_types() -> None:
    """Test all IngestionResultType values."""
    assert IngestionResultType.SUCCESS.value == "success"
    assert IngestionResultType.SKIPPED.value == "skipped"
    assert IngestionResultType.FAILED.value == "failed"
    assert IngestionResultType.QUARANTINED.value == "quarantined"


async def test_batch_ingestion_result() -> None:
    """Test BatchIngestionResult aggregation."""
    batch = BatchIngestionResult(total_symbols=5)

    result1 = IngestionResult(
        dataset_id="test-1",
        provider_name="p1",
        result_type=IngestionResultType.SUCCESS,
        records_fetched=10,
        records_stored=10,
    )
    result2 = IngestionResult(
        dataset_id="test-2",
        provider_name="p1",
        result_type=IngestionResultType.FAILED,
        records_fetched=5,
        error_message="Connection error",
    )
    result3 = IngestionResult(
        dataset_id="test-3",
        provider_name="p1",
        result_type=IngestionResultType.SKIPPED,
        records_fetched=0,
    )

    batch.add_result(result1)
    batch.add_result(result2)
    batch.add_result(result3)

    assert batch.total_symbols == 5
    assert batch.successful == 1
    assert batch.failed == 1
    assert batch.skipped == 1
    assert batch.total_records_fetched == 15
    assert batch.total_records_stored == 10
    assert len(batch.error_messages) == 1
    assert "Connection error" in batch.error_messages[0]

    summary = batch.summary()
    assert "1 success" in summary
    assert "1 failed" in summary
    assert "1 skipped" in summary
    assert "15 fetched" in summary
    assert "10 stored" in summary


async def test_batch_ingestion_result_quarantined() -> None:
    """Test BatchIngestionResult with quarantined results."""
    batch = BatchIngestionResult(total_symbols=2)

    result1 = IngestionResult(
        dataset_id="test-1",
        provider_name="p1",
        result_type=IngestionResultType.QUARANTINED,
        records_fetched=10,
        records_stored=0,
    )
    result2 = IngestionResult(
        dataset_id="test-2",
        provider_name="p1",
        result_type=IngestionResultType.SUCCESS,
        records_fetched=5,
        records_stored=5,
    )

    batch.add_result(result1)
    batch.add_result(result2)

    assert batch.quarantined == 1
    assert batch.successful == 1
    assert batch.total_records_fetched == 15
    assert batch.total_records_stored == 5