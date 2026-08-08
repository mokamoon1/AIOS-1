"""Tests for mock data providers (AIOS-603 section 6)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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
from aios.database.exceptions import RecordNotFoundError
from aios.providers import (
    DataProvider,
    FundamentalDataProvider,
    MarketDataProvider,
    MockFundamentalDataProvider,
    MockMarketDataProvider,
    MockShariahDataProvider,
    ShariahDataProvider,
)


class _FakeMarketRepository:
    """In-memory fake for MarketRepository."""

    def __init__(self) -> None:
        self._candles: dict[tuple[str, Timeframe], list[Candle]] = {}
        self._securities: dict[tuple[str, str], Security] = {}

    def add_candles(self, candles: list[Candle], provider: str) -> int:
        for candle in candles:
            key = (candle.symbol, candle.timeframe)
            if key not in self._candles:
                self._candles[key] = []
            self._candles[key].append(candle)
        return len(candles)

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        key = (symbol, timeframe)
        candles = self._candles.get(key, [])
        if start is not None:
            candles = [c for c in candles if c.timestamp >= start]
        if end is not None:
            candles = [c for c in candles if c.timestamp <= end]
        return candles[:limit]

    def add_security(self, security: Security) -> None:
        self._securities[(security.symbol, security.exchange)] = security

    def get_security(self, symbol: str, exchange: str) -> Security:
        key = (symbol, exchange)
        if key not in self._securities:
            raise RecordNotFoundError(f"Security {symbol!r} on {exchange!r} not found")
        return self._securities[key]


class _FakeShariahRepository:
    """In-memory fake for ShariahRepository."""

    def __init__(self) -> None:
        self._records: dict[str, list[ShariahCompliance]] = {}

    def add_records(self, records: list[ShariahCompliance]) -> int:
        for record in records:
            if record.symbol not in self._records:
                self._records[record.symbol] = []
            self._records[record.symbol].append(record)
        return len(records)

    def get_compliance_status(self, symbol: str, *, as_of: date | None = None) -> ShariahCompliance:
        if symbol not in self._records or not self._records[symbol]:
            raise RecordNotFoundError(f"No compliance record for {symbol!r} as of {as_of}")
        # Return the latest effective record
        records = self._records[symbol]
        if as_of is not None:
            records = [r for r in records if r.effective_date <= as_of]
            if not records:
                raise RecordNotFoundError(f"No compliance record for {symbol!r} as of {as_of}")
        return max(records, key=lambda r: (r.effective_date, r.retrieval_timestamp))


class _FakeCompanyRepository:
    """In-memory fake for CompanyRepository."""

    def __init__(self) -> None:
        self._records: dict[str, list[CompanyFundamentals]] = {}

    def add_fundamentals(self, records: list[CompanyFundamentals]) -> int:
        for record in records:
            if record.symbol not in self._records:
                self._records[record.symbol] = []
            self._records[record.symbol].append(record)
        return len(records)

    def get_fundamentals(
        self, symbol: str, *, report_date: date | None = None
    ) -> CompanyFundamentals:
        if symbol not in self._records or not self._records[symbol]:
            raise RecordNotFoundError(f"No fundamentals for {symbol!r}")
        records = self._records[symbol]
        if report_date is not None:
            records = [r for r in records if r.report_date == report_date]
            if not records:
                raise RecordNotFoundError(f"No fundamentals for {symbol!r}")
        return max(records, key=lambda r: r.report_date)


# Import date for the fake repositories
from datetime import date


async def test_mock_market_provider_protocol_conformance() -> None:
    """Verify MockMarketDataProvider conforms to protocols."""
    repo = _FakeMarketRepository()
    provider = MockMarketDataProvider(repo)
    assert isinstance(provider, MarketDataProvider)
    assert isinstance(provider, DataProvider)
    assert provider.name == "mock-market"


async def test_mock_shariah_provider_protocol_conformance() -> None:
    """Verify MockShariahDataProvider conforms to protocols."""
    repo = _FakeShariahRepository()
    provider = MockShariahDataProvider(repo)
    assert isinstance(provider, ShariahDataProvider)
    assert isinstance(provider, DataProvider)
    assert provider.name == "mock-shariah"


async def test_mock_fundamental_provider_protocol_conformance() -> None:
    """Verify MockFundamentalDataProvider conforms to protocols."""
    repo = _FakeCompanyRepository()
    provider = MockFundamentalDataProvider(repo)
    assert isinstance(provider, FundamentalDataProvider)
    assert isinstance(provider, DataProvider)
    assert provider.name == "mock-fundamental"


async def test_mock_market_provider_connect_disconnect() -> None:
    """Test connect/disconnect/is_connected lifecycle."""
    repo = _FakeMarketRepository()
    provider = MockMarketDataProvider(repo)

    assert not provider.is_connected()
    await provider.connect()
    assert provider.is_connected()
    await provider.disconnect()
    assert not provider.is_connected()


async def test_mock_shariah_provider_connect_disconnect() -> None:
    """Test connect/disconnect/is_connected lifecycle."""
    repo = _FakeShariahRepository()
    provider = MockShariahDataProvider(repo)

    assert not provider.is_connected()
    await provider.connect()
    assert provider.is_connected()
    await provider.disconnect()
    assert not provider.is_connected()


async def test_mock_fundamental_provider_connect_disconnect() -> None:
    """Test connect/disconnect/is_connected lifecycle."""
    repo = _FakeCompanyRepository()
    provider = MockFundamentalDataProvider(repo)

    assert not provider.is_connected()
    await provider.connect()
    assert provider.is_connected()
    await provider.disconnect()
    assert not provider.is_connected()


async def test_mock_market_provider_get_candles() -> None:
    """Test get_candles returns candles from repository."""
    repo = _FakeMarketRepository()
    provider = MockMarketDataProvider(repo)

    # Seed data
    candle = Candle(
        timestamp=datetime(2026, 8, 1, 13, 30, tzinfo=timezone.utc),
        symbol="AAPL",
        timeframe=Timeframe.ONE_DAY,
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000.0,
    )
    repo.add_candles([candle], "test")

    candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY)
    assert len(candles) == 1
    assert candles[0].symbol == "AAPL"
    assert candles[0].timeframe == Timeframe.ONE_DAY
    assert candles[0].close == 104.0


async def test_mock_market_provider_get_candles_with_filters() -> None:
    """Test get_candles with start/end/limit filters."""
    repo = _FakeMarketRepository()
    provider = MockMarketDataProvider(repo)

    # Seed multiple candles with different dates
    base = datetime(2026, 8, 1, 13, 30, tzinfo=timezone.utc)
    for i in range(5):
        candle = Candle(
            timestamp=base + timedelta(days=i),
            symbol="MSFT",
            timeframe=Timeframe.ONE_DAY,
            open=100.0 + i,
            high=105.0 + i,
            low=99.0 + i,
            close=104.0 + i,
            volume=1000.0,
        )
        repo.add_candles([candle], "test")

    # Test limit
    candles = await provider.get_candles("MSFT", Timeframe.ONE_DAY, limit=2)
    assert len(candles) == 2

    # Test start filter
    start = datetime(2026, 8, 3, 13, 30, tzinfo=timezone.utc)
    candles = await provider.get_candles("MSFT", Timeframe.ONE_DAY, start=start)
    assert len(candles) == 3  # days 3, 4, 5


async def test_mock_market_provider_get_security() -> None:
    """Test get_security returns security from repository."""
    repo = _FakeMarketRepository()
    provider = MockMarketDataProvider(repo)

    # Seed data
    security = Security(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_type=AssetType.EQUITY,
        currency="USD",
        trading_session="regular",
        timezone="America/New_York",
        market_status="open",
    )
    repo.add_security(security)

    result = await provider.get_security("AAPL", "NASDAQ")
    assert result.symbol == "AAPL"
    assert result.exchange == "NASDAQ"
    assert result.asset_type == AssetType.EQUITY


async def test_mock_market_provider_get_security_not_found() -> None:
    """Test get_security raises RecordNotFoundError for missing security."""
    repo = _FakeMarketRepository()
    provider = MockMarketDataProvider(repo)

    with pytest.raises(RecordNotFoundError):
        await provider.get_security("UNKNOWN", "NASDAQ")


async def test_mock_shariah_provider_get_compliance() -> None:
    """Test get_compliance returns compliance record from repository."""
    repo = _FakeShariahRepository()
    provider = MockShariahDataProvider(repo)

    # Seed data
    record = ShariahCompliance(
        symbol="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        country="US",
        asset_type=AssetType.EQUITY,
        compliance_status=ComplianceStatus.COMPLIANT,
        provider="mock-shariah",
        review_date=date(2026, 7, 1),
        effective_date=date(2026, 7, 1),
        screening_methodology="test",
        screening_date=date(2026, 7, 1),
    )
    repo.add_records([record])

    result = await provider.get_compliance("AAPL")
    assert result.symbol == "AAPL"
    assert result.compliance_status == ComplianceStatus.COMPLIANT
    assert result.provider == "mock-shariah"


async def test_mock_shariah_provider_get_compliance_not_found() -> None:
    """Test get_compliance raises RecordNotFoundError for missing compliance."""
    repo = _FakeShariahRepository()
    provider = MockShariahDataProvider(repo)

    with pytest.raises(RecordNotFoundError):
        await provider.get_compliance("UNKNOWN")


async def test_mock_shariah_provider_get_compliance_history() -> None:
    """Test get_compliance_history returns list of compliance records."""
    repo = _FakeShariahRepository()
    provider = MockShariahDataProvider(repo)

    # Seed multiple records
    for i in range(3):
        record = ShariahCompliance(
            symbol="MSFT",
            company_name="Microsoft",
            exchange="NASDAQ",
            country="US",
            asset_type=AssetType.EQUITY,
            compliance_status=ComplianceStatus.COMPLIANT,
            provider="mock-shariah",
            review_date=date(2026, 7, 1 + i),
            effective_date=date(2026, 7, 1 + i),
            screening_methodology="test",
            screening_date=date(2026, 7, 1 + i),
        )
        repo.add_records([record])

    history = await provider.get_compliance_history("MSFT")
    assert len(history) == 1  # Returns latest only (current implementation)
    assert history[0].symbol == "MSFT"


async def test_mock_fundamental_provider_get_fundamentals() -> None:
    """Test get_fundamentals returns fundamentals from repository."""
    repo = _FakeCompanyRepository()
    provider = MockFundamentalDataProvider(repo)

    # Seed data
    fundamentals = CompanyFundamentals(
        symbol="AAPL",
        sector="Technology",
        industry="Software",
        revenue=1000.0,
        net_income=200.0,
        eps=2.5,
        report_date=date(2026, 6, 30),
    )
    repo.add_fundamentals([fundamentals])

    result = await provider.get_fundamentals("AAPL")
    assert result.symbol == "AAPL"
    assert result.revenue == 1000.0
    assert result.sector == "Technology"


async def test_mock_fundamental_provider_get_fundamentals_not_found() -> None:
    """Test get_fundamentals raises RecordNotFoundError for missing fundamentals."""
    repo = _FakeCompanyRepository()
    provider = MockFundamentalDataProvider(repo)

    with pytest.raises(RecordNotFoundError):
        await provider.get_fundamentals("UNKNOWN")


async def test_all_mock_providers_with_provider_manager() -> None:
    """Test all mock providers work with ProviderManager."""
    from aios.providers.base import ProviderManager

    market_repo = _FakeMarketRepository()
    shariah_repo = _FakeShariahRepository()
    company_repo = _FakeCompanyRepository()

    market_provider = MockMarketDataProvider(market_repo)
    shariah_provider = MockShariahDataProvider(shariah_repo)
    fundamental_provider = MockFundamentalDataProvider(company_repo)

    manager = ProviderManager()
    manager.register(market_provider)
    manager.register(shariah_provider)
    manager.register(fundamental_provider)

    assert len(manager.list_providers()) == 3
    assert manager.status() == {
        "mock-market": False,
        "mock-shariah": False,
        "mock-fundamental": False,
    }

    await manager.connect_all()
    assert all(manager.status().values())

    await manager.disconnect_all()
    assert not any(manager.status().values())