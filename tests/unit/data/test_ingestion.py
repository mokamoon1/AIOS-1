"""Tests for IngestionService (AIOS-505, Phase 8)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from aios.data.ingestion import IngestionConfig, IngestionService
from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.data.pipeline import DataPipeline
from aios.data.validation import DataValidator, ValidationResult
from aios.providers.adapter import IngestionResultType


class _FakeMarketAdapter:
    """Fake market adapter for testing."""

    name = "fake-market"
    provider_name = "fake-market"

    def __init__(self):
        self.fetch_candles_mock = AsyncMock()
        self.fetch_security_mock = AsyncMock()

    async def fetch_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000):
        return await self.fetch_candles_mock(symbol, timeframe, start=start, end=end, limit=limit)

    async def fetch_security(self, symbol, exchange):
        return await self.fetch_security_mock(symbol, exchange)


class _FakeShariahAdapter:
    """Fake Shariah adapter for testing."""

    name = "fake-shariah"
    provider_name = "fake-shariah"

    def __init__(self):
        self.fetch_compliance_mock = AsyncMock()

    async def fetch_compliance(self, symbol):
        return await self.fetch_compliance_mock(symbol)

    async def fetch_compliance_history(self, symbol, *, since=None):
        return []


class _FakeFundamentalAdapter:
    """Fake fundamental adapter for testing."""

    name = "fake-fundamental"
    provider_name = "fake-fundamental"

    def __init__(self):
        self.fetch_fundamentals_mock = AsyncMock()

    async def fetch_fundamentals(self, symbol):
        return await self.fetch_fundamentals_mock(symbol)


class _FakeMarketRepo:
    """Fake market repository for testing."""

    def __init__(self):
        self.add_candles_mock = MagicMock(return_value=1)
        self.add_security_mock = MagicMock()

    def add_candles(self, candles, provider):
        return self.add_candles_mock(candles, provider)

    def add_security(self, security):
        return self.add_security_mock(security)


class _FakeShariahRepo:
    """Fake Shariah repository for testing."""

    def __init__(self):
        self.add_records_mock = MagicMock(return_value=1)

    def add_records(self, records):
        return self.add_records_mock(records)


class _FakeFundamentalRepo:
    """Fake fundamental repository for testing."""

    def __init__(self):
        self.add_fundamentals_mock = MagicMock(return_value=1)

    def add_fundamentals(self, records):
        return self.add_fundamentals_mock(records)


@pytest.fixture
def market_adapter():
    return _FakeMarketAdapter()


@pytest.fixture
def shariah_adapter():
    return _FakeShariahAdapter()


@pytest.fixture
def fundamental_adapter():
    return _FakeFundamentalAdapter()


@pytest.fixture
def market_repo():
    return _FakeMarketRepo()


@pytest.fixture
def shariah_repo():
    return _FakeShariahRepo()


@pytest.fixture
def fundamental_repo():
    return _FakeFundamentalRepo()


@pytest.fixture
def pipeline():
    return DataPipeline(DataValidator())


@pytest.fixture
def validator():
    return DataValidator()


@pytest.fixture
def ingestion_service(pipeline, validator, market_adapter, shariah_adapter, fundamental_adapter,
                      market_repo, shariah_repo, fundamental_repo):
    return IngestionService(
        pipeline=pipeline,
        validator=validator,
        market_adapter=market_adapter,
        shariah_adapter=shariah_adapter,
        fundamental_adapter=fundamental_adapter,
        market_repository=market_repo,
        shariah_repository=shariah_repo,
        fundamental_repository=fundamental_repo,
    )


async def make_candle(symbol="AAPL", timeframe=Timeframe.ONE_DAY, offset_days=0):
    base = datetime(2026, 8, 1, 13, 30, tzinfo=timezone.utc)
    return Candle(
        timestamp=base + timedelta(days=offset_days),
        symbol=symbol,
        timeframe=timeframe,
        open=100.0 + offset_days,
        high=105.0 + offset_days,
        low=99.0 + offset_days,
        close=104.0 + offset_days,
        volume=1000.0,
    )


async def make_security(symbol="AAPL", exchange="NASDAQ"):
    return Security(
        symbol=symbol,
        exchange=exchange,
        asset_type=AssetType.EQUITY,
        currency="USD",
        trading_session="regular",
        timezone="America/New_York",
        market_status="open",
    )


async def make_compliance(symbol="AAPL"):
    return ShariahCompliance(
        symbol=symbol,
        company_name="Apple Inc.",
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


async def make_fundamentals(symbol="AAPL"):
    return CompanyFundamentals(
        symbol=symbol,
        sector="Technology",
        industry="Software",
        revenue=1000.0,
        net_income=200.0,
        eps=2.5,
        report_date=date(2026, 6, 30),
    )


async def test_ingestion_service_creation(ingestion_service):
    """Test IngestionService can be created with all components."""
    assert ingestion_service._market_adapter is not None
    assert ingestion_service._shariah_adapter is not None
    assert ingestion_service._fundamental_adapter is not None
    assert ingestion_service._market_repo is not None
    assert ingestion_service._shariah_repo is not None
    assert ingestion_service._fundamental_repo is not None


async def test_ingest_market_data_success(ingestion_service, market_adapter, market_repo):
    """Test successful market data ingestion."""
    candle = await make_candle()
    security = await make_security()

    market_adapter.fetch_candles_mock.return_value = [candle]
    market_adapter.fetch_security_mock.return_value = security
    market_repo.add_candles_mock.return_value = 1

    result = await ingestion_service.ingest_market_data(
        "AAPL", Timeframe.ONE_DAY, limit=1
    )

    assert result.result_type == IngestionResultType.SUCCESS
    assert result.records_fetched == 1
    assert result.records_stored == 1
    assert result.provider_name == "fake-market"
    market_adapter.fetch_candles_mock.assert_called_once()
    market_adapter.fetch_security_mock.assert_called_once_with("AAPL", "NASDAQ")
    market_repo.add_candles_mock.assert_called_once()
    market_repo.add_security_mock.assert_called_once_with(security)


async def test_ingest_market_data_no_candles(ingestion_service, market_adapter):
    """Test market data ingestion with no candles returned."""
    market_adapter.fetch_candles_mock.return_value = []

    result = await ingestion_service.ingest_market_data("AAPL", Timeframe.ONE_DAY)

    assert result.result_type == IngestionResultType.SKIPPED
    assert result.records_fetched == 0
    assert "No candles returned" in result.error_message


async def test_ingest_market_data_no_adapter(ingestion_service):
    """Test market data ingestion with no adapter configured."""
    ingestion_service._market_adapter = None

    result = await ingestion_service.ingest_market_data("AAPL", Timeframe.ONE_DAY)

    assert result.result_type == IngestionResultType.SKIPPED
    assert "Market adapter or repository not configured" in result.error_message


async def test_ingest_shariah_data_success(ingestion_service, shariah_adapter, shariah_repo):
    """Test successful Shariah data ingestion."""
    compliance = await make_compliance()

    shariah_adapter.fetch_compliance_mock.return_value = compliance
    shariah_repo.add_records_mock.return_value = 1

    result = await ingestion_service.ingest_shariah_data("AAPL")

    assert result.result_type == IngestionResultType.SUCCESS
    assert result.records_fetched == 1
    assert result.records_stored == 1
    assert result.provider_name == "fake-shariah"
    shariah_adapter.fetch_compliance_mock.assert_called_once_with("AAPL")
    shariah_repo.add_records_mock.assert_called_once()


async def test_ingest_shariah_data_quarantined(ingestion_service, shariah_adapter):
    """Test Shariah data ingestion with quarantined validation."""
    from aios.data.models import ShariahCompliance
    from aios.data.validation import ValidationResult

    # Create a record that will trigger quarantine (future review date)
    bad_compliance = ShariahCompliance(
        symbol="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        country="US",
        asset_type=AssetType.EQUITY,
        compliance_status=ComplianceStatus.COMPLIANT,
        provider="fake-shariah",
        review_date=date(2030, 1, 1),  # Future date triggers warning/quarantine
        effective_date=date(2026, 7, 1),
        screening_methodology="test",
        screening_date=date(2026, 7, 1),
    )
    shariah_adapter.fetch_compliance_mock.return_value = bad_compliance

    result = await ingestion_service.ingest_shariah_data("AAPL")

    # Should be quarantined due to future review date
    assert result.result_type == IngestionResultType.QUARANTINED


async def test_ingest_shariah_data_no_adapter(ingestion_service):
    """Test Shariah data ingestion with no adapter."""
    ingestion_service._shariah_adapter = None

    result = await ingestion_service.ingest_shariah_data("AAPL")

    assert result.result_type == IngestionResultType.SKIPPED
    assert "Shariah adapter or repository not configured" in result.error_message


async def test_ingest_fundamentals_success(ingestion_service, fundamental_adapter, fundamental_repo):
    """Test successful fundamentals ingestion."""
    fundamentals = await make_fundamentals()

    fundamental_adapter.fetch_fundamentals_mock.return_value = fundamentals
    fundamental_repo.add_fundamentals_mock.return_value = 1

    result = await ingestion_service.ingest_fundamentals("AAPL")

    assert result.result_type == IngestionResultType.SUCCESS
    assert result.records_fetched == 1
    assert result.records_stored == 1
    assert result.provider_name == "fake-fundamental"
    fundamental_adapter.fetch_fundamentals_mock.assert_called_once_with("AAPL")
    fundamental_repo.add_fundamentals_mock.assert_called_once()


async def test_ingest_fundamentals_no_adapter(ingestion_service):
    """Test fundamentals ingestion with no adapter."""
    ingestion_service._fundamental_adapter = None

    result = await ingestion_service.ingest_fundamentals("AAPL")

    assert result.result_type == IngestionResultType.SKIPPED
    assert "Fundamental adapter or repository not configured" in result.error_message


async def test_ingestion_config_defaults():
    """Test IngestionConfig default values."""
    config = IngestionConfig()
    assert config.batch_size == 100
    assert config.rate_limit_ms == 0
    assert config.max_concurrent == 1
    assert config.quarantine_on_warning is False
    assert config.freshness_max_age_days is None


async def test_ingestion_config_custom():
    """Test IngestionConfig with custom values."""
    config = IngestionConfig(
        batch_size=50,
        rate_limit_ms=100,
        max_concurrent=2,
        quarantine_on_warning=True,
        freshness_max_age_days=7,
    )
    assert config.batch_size == 50
    assert config.rate_limit_ms == 100
    assert config.max_concurrent == 2
    assert config.quarantine_on_warning is True
    assert config.freshness_max_age_days == 7


async def test_ingestion_service_config(ingestion_service):
    """Test IngestionService exposes config."""
    assert ingestion_service.config.batch_size == 100
    assert ingestion_service.config.rate_limit_ms == 0


async def test_ingestion_service_is_configured(ingestion_service):
    """Test is_configured property."""
    assert ingestion_service.is_configured is True


async def test_ingestion_service_adapter_status(ingestion_service):
    """Test get_adapter_status method."""
    status = ingestion_service.get_adapter_status()
    assert status["market"] is True
    assert status["shariah"] is True
    assert status["fundamental"] is True


async def test_ingestion_service_partial_config(pipeline, validator, market_adapter, market_repo):
    """Test IngestionService with only market adapter configured."""
    service = IngestionService(
        pipeline=pipeline,
        validator=validator,
        market_adapter=market_adapter,
        market_repository=market_repo,
    )
    status = service.get_adapter_status()
    assert status["market"] is True
    assert status["shariah"] is False
    assert status["fundamental"] is False
    assert service.is_configured is True


async def test_historical_market_data_batch(ingestion_service, market_adapter, market_repo):
    """Test historical market data batch ingestion."""
    symbols = ["AAPL", "MSFT", "GOOGL"]
    candles = [await make_candle(s) for s in symbols]
    securities = [await make_security(s) for s in symbols]

    def fetch_side_effect(symbol, timeframe, **kwargs):
        idx = symbols.index(symbol)
        return [candles[idx]]

    market_adapter.fetch_candles_mock.side_effect = fetch_side_effect
    market_adapter.fetch_security_mock.side_effect = lambda s, e: securities[symbols.index(s)]
    market_repo.add_candles_mock.return_value = 1

    start_date = date(2026, 8, 1)
    end_date = date(2026, 8, 5)

    result = await ingestion_service.ingest_historical_market_data(
        symbols, Timeframe.ONE_DAY, start_date, end_date, batch_size=2
    )

    assert result.total_symbols == 3
    assert result.successful == 3
    assert result.total_records_fetched == 3
    assert result.total_records_stored == 3
    assert market_adapter.fetch_candles_mock.call_count == 3


async def test_historical_shariah_data_batch(ingestion_service, shariah_adapter, shariah_repo):
    """Test historical Shariah data batch ingestion."""
    symbols = ["AAPL", "MSFT", "GOOGL"]
    compliances = [await make_compliance(s) for s in symbols]

    def fetch_side_effect(symbol):
        return compliances[symbols.index(symbol)]

    shariah_adapter.fetch_compliance_mock.side_effect = fetch_side_effect
    shariah_repo.add_records_mock.return_value = 1

    result = await ingestion_service.ingest_historical_shariah_data(symbols, batch_size=2)

    assert result.total_symbols == 3
    assert result.successful == 3
    assert shariah_adapter.fetch_compliance_mock.call_count == 3


async def test_historical_fundamentals_batch(ingestion_service, fundamental_adapter, fundamental_repo):
    """Test historical fundamentals batch ingestion."""
    symbols = ["AAPL", "MSFT", "GOOGL"]
    fundamentals_list = [await make_fundamentals(s) for s in symbols]

    def fetch_side_effect(symbol):
        return fundamentals_list[symbols.index(symbol)]

    fundamental_adapter.fetch_fundamentals_mock.side_effect = fetch_side_effect
    fundamental_repo.add_fundamentals_mock.return_value = 1

    result = await ingestion_service.ingest_historical_fundamentals(symbols, batch_size=2)

    assert result.total_symbols == 3
    assert result.successful == 3
    assert fundamental_adapter.fetch_fundamentals_mock.call_count == 3


async def test_historical_batch_progress_callback(ingestion_service, market_adapter, market_repo):
    """Test progress callback in batch ingestion."""
    symbols = ["AAPL", "MSFT", "GOOGL"]
    candles = [await make_candle(s) for s in symbols]
    securities = [await make_security(s) for s in symbols]

    def fetch_side_effect(symbol, timeframe, **kwargs):
        idx = symbols.index(symbol)
        return [candles[idx]]

    market_adapter.fetch_candles_mock.side_effect = fetch_side_effect
    market_adapter.fetch_security_mock.side_effect = lambda s, e: securities[symbols.index(s)]
    market_repo.add_candles_mock.return_value = 1

    progress_calls = []

    def callback(completed, total, current):
        progress_calls.append((completed, total, current))

    await ingestion_service.ingest_historical_market_data(
        symbols, Timeframe.ONE_DAY, date(2026, 8, 1), date(2026, 8, 5),
        batch_size=2, progress_callback=callback
    )

    # Should have 2 batch callbacks (batch of 2, then batch of 1)
    assert len(progress_calls) == 2
    assert progress_calls[0] == (2, 3, "MSFT")
    assert progress_calls[1] == (3, 3, "GOOGL")