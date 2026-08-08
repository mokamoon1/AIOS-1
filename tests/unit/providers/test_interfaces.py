"""Provider interface tests (AIOS-603 section 6, AIOS-607)."""

from __future__ import annotations

from datetime import datetime, timezone

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
from aios.providers import (
    DataProvider,
    FundamentalDataProvider,
    MarketDataProvider,
    ProviderManager,
    ShariahDataProvider,
)
from aios.providers.exceptions import ProviderNotFoundError, ProviderRegistrationError

pytestmark = pytest.mark.unit


class FakeMarketProvider:
    """A provider stub returning standardized models (AIOS-607 section 11)."""

    name = "fake-market"

    def __init__(self) -> None:
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def get_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000):
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

    async def get_security(self, symbol, exchange):
        return Security(
            symbol=symbol,
            exchange=exchange,
            asset_type=AssetType.EQUITY,
            currency="USD",
            trading_session="regular",
            timezone="America/New_York",
            market_status="open",
        )


class FakeShariahProvider:
    name = "fake-shariah"

    def __init__(self) -> None:
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def get_compliance(self, symbol):
        return ShariahCompliance(
            symbol=symbol,
            company_name="Test Corp",
            exchange="NASDAQ",
            country="US",
            asset_type=AssetType.EQUITY,
            compliance_status=ComplianceStatus.COMPLIANT,
            provider=self.name,
            review_date="2026-07-01",
            effective_date="2026-07-01",
            screening_methodology="test",
            screening_date="2026-07-01",
        )

    async def get_compliance_history(self, symbol, *, since=None):
        return [await self.get_compliance(symbol)]


class FakeFundamentalProvider:
    name = "fake-fundamental"

    def __init__(self) -> None:
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def get_fundamentals(self, symbol):
        return CompanyFundamentals(symbol=symbol, report_date="2026-06-30", revenue=100.0)


class TestProviderInterfaces:
    def test_market_provider_is_protocol(self) -> None:
        assert isinstance(MarketDataProvider, type)
        assert isinstance(DataProvider, type)

    def test_fake_providers_conform(self) -> None:
        assert isinstance(FakeMarketProvider(), MarketDataProvider)
        assert isinstance(FakeMarketProvider(), DataProvider)
        assert isinstance(FakeShariahProvider(), ShariahDataProvider)
        assert isinstance(FakeFundamentalProvider(), FundamentalDataProvider)

    async def test_market_provider_returns_standardized_models(self) -> None:
        provider = FakeMarketProvider()
        candles = await provider.get_candles("AAPL", Timeframe.ONE_HOUR)
        assert all(isinstance(c, Candle) for c in candles)
        assert candles[0].symbol == "AAPL"
        security = await provider.get_security("AAPL", "NASDAQ")
        assert isinstance(security, Security)

    async def test_shariah_provider_returns_standardized_model(self) -> None:
        provider = FakeShariahProvider()
        record = await provider.get_compliance("AAPL")
        assert isinstance(record, ShariahCompliance)
        assert record.provider == "fake-shariah"

    async def test_fundamental_provider_returns_standardized_model(self) -> None:
        provider = FakeFundamentalProvider()
        record = await provider.get_fundamentals("AAPL")
        assert isinstance(record, CompanyFundamentals)


class TestProviderManager:
    async def test_register_and_status(self) -> None:
        manager = ProviderManager()
        provider = FakeMarketProvider()
        manager.register(provider)
        assert manager.status() == {"fake-market": False}
        await manager.connect_all()
        assert manager.status() == {"fake-market": True}
        await manager.disconnect_all()
        assert manager.status() == {"fake-market": False}

    def test_duplicate_registration_raises(self) -> None:
        manager = ProviderManager()
        manager.register(FakeMarketProvider())
        with pytest.raises(ProviderRegistrationError):
            manager.register(FakeMarketProvider())

    def test_unregister_and_get(self) -> None:
        manager = ProviderManager()
        provider = FakeMarketProvider()
        manager.register(provider)
        assert manager.get("fake-market") is provider
        manager.unregister("fake-market")
        with pytest.raises(ProviderNotFoundError):
            manager.get("fake-market")

    def test_list_providers_order(self) -> None:
        manager = ProviderManager()
        market = FakeMarketProvider()
        shariah = FakeShariahProvider()
        manager.register(market)
        manager.register(shariah)
        assert manager.list_providers() == [market, shariah]
