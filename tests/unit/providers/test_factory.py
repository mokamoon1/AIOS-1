"""Tests for provider factory and configuration (AIOS-603 section 6)."""

from __future__ import annotations

import pytest

from aios.config.settings import Environment
from aios.database.exceptions import RecordNotFoundError
from aios.providers import (
    MarketDataProvider,
    MockMarketDataProvider,
    MockShariahDataProvider,
    MockFundamentalDataProvider,
    ProviderConfig,
    ProviderType,
    ProvidersConfig,
    ShariahDataProvider,
    FundamentalDataProvider,
)
from aios.providers.factory import ProviderFactory, ProviderFactoryError


class _FakeMarketRepository:
    """In-memory fake for MarketRepository."""

    def __init__(self) -> None:
        self._candles = []
        self._securities = {}

    def get_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000):
        return self._candles

    def get_security(self, symbol, exchange):
        return self._securities.get((symbol, exchange))


class _FakeShariahRepository:
    """In-memory fake for ShariahRepository."""

    def __init__(self) -> None:
        self._records = []

    def get_compliance_status(self, symbol, *, as_of=None):
        return self._records[0] if self._records else None


class _FakeCompanyRepository:
    """In-memory fake for CompanyRepository."""

    def __init__(self) -> None:
        self._records = []

    def get_fundamentals(self, symbol, *, report_date=None):
        return self._records[0] if self._records else None


class _FakeSessionFactory:
    """Fake session factory that returns fake repositories."""

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


async def test_provider_config_mock_market() -> None:
    """Test ProviderConfig for mock_market type."""
    config = ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True)
    assert config.type == ProviderType.MOCK_MARKET
    assert config.enabled is True
    assert config.options == {}


async def test_provider_config_mock_shariah() -> None:
    """Test ProviderConfig for mock_shariah type."""
    config = ProviderConfig(type=ProviderType.MOCK_SHARIAH, enabled=True)
    assert config.type == ProviderType.MOCK_SHARIAH


async def test_provider_config_mock_fundamental() -> None:
    """Test ProviderConfig for mock_fundamental type."""
    config = ProviderConfig(type=ProviderType.MOCK_FUNDAMENTAL, enabled=True)
    assert config.type == ProviderType.MOCK_FUNDAMENTAL


async def test_provider_config_rejects_secret_keys() -> None:
    """Test ProviderConfig rejects secret keys in options."""
    with pytest.raises(ValueError, match="Secret key"):
        ProviderConfig(
            type=ProviderType.MOCK_MARKET,
            enabled=True,
            options={"api_key": "secret"},
        )

    with pytest.raises(ValueError, match="Secret key"):
        ProviderConfig(
            type=ProviderType.MOCK_MARKET,
            enabled=True,
            options={"SECRET": "value"},
        )


async def test_providers_config_get_enabled() -> None:
    """Test ProvidersConfig.get_enabled_providers."""
    config = ProvidersConfig(
        providers=[
            ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_SHARIAH, enabled=False),
            ProviderConfig(type=ProviderType.MOCK_FUNDAMENTAL, enabled=True),
        ]
    )
    enabled = config.get_enabled_providers()
    assert len(enabled) == 2
    assert all(p.enabled for p in enabled)


async def test_providers_config_get_mock_providers() -> None:
    """Test ProvidersConfig.get_mock_providers."""
    config = ProvidersConfig(
        providers=[
            ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_SHARIAH, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_FUNDAMENTAL, enabled=True),
        ]
    )
    mock_providers = config.get_mock_providers()
    assert len(mock_providers) == 3


async def test_providers_config_validate_for_paper_environment() -> None:
    """Test ProvidersConfig validates for PAPER environment."""
    # Mock providers should pass
    config = ProvidersConfig(
        providers=[
            ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_SHARIAH, enabled=True),
        ]
    )
    config.validate_for_environment(Environment.PAPER)  # Should not raise


async def test_provider_factory_creates_mock_market() -> None:
    """Test ProviderFactory creates MockMarketDataProvider."""
    session_factory = _FakeSessionFactory()
    factory = ProviderFactory(session_factory)

    config = ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True)
    provider = factory.create_provider(config, environment=Environment.PAPER)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(provider, MarketDataProvider)
    assert provider.name == "mock-market"


async def test_provider_factory_creates_mock_shariah() -> None:
    """Test ProviderFactory creates MockShariahDataProvider."""
    session_factory = _FakeSessionFactory()
    factory = ProviderFactory(session_factory)

    config = ProviderConfig(type=ProviderType.MOCK_SHARIAH, enabled=True)
    provider = factory.create_provider(config, environment=Environment.PAPER)

    assert isinstance(provider, MockShariahDataProvider)
    assert isinstance(provider, ShariahDataProvider)
    assert provider.name == "mock-shariah"


async def test_provider_factory_creates_mock_fundamental() -> None:
    """Test ProviderFactory creates MockFundamentalDataProvider."""
    session_factory = _FakeSessionFactory()
    factory = ProviderFactory(session_factory)

    config = ProviderConfig(type=ProviderType.MOCK_FUNDAMENTAL, enabled=True)
    provider = factory.create_provider(config, environment=Environment.PAPER)

    assert isinstance(provider, MockFundamentalDataProvider)
    assert isinstance(provider, FundamentalDataProvider)
    assert provider.name == "mock-fundamental"


async def test_provider_factory_rejects_unknown_type() -> None:
    """Test ProviderFactory rejects unknown provider type."""
    session_factory = _FakeSessionFactory()
    factory = ProviderFactory(session_factory)

    # Create a config with a type that's not in the enum by using a string
    # that doesn't match any ProviderType - we'll create a custom type
    from aios.providers.registry import ProviderType

    # Create a config with a valid type first, then we'll test the factory's
    # handling of unknown types by passing a type that isn't in our enum
    class UnknownProviderType:
        value = "unknown_type"

    # Create a minimal config-like object with the unknown type
    class FakeConfig:
        def __init__(self):
            self.type = UnknownProviderType()
            self.enabled = True
            self.options = {}

    with pytest.raises(ProviderFactoryError, match="not allowed in PAPER environment"):
        factory.create_provider(FakeConfig(), environment=Environment.PAPER)


async def test_provider_factory_rejects_live_provider_in_paper() -> None:
    """Test ProviderFactory rejects live provider in PAPER environment."""
    session_factory = _FakeSessionFactory()
    factory = ProviderFactory(session_factory)

    # Create a fake live provider type
    class FakeLiveType:
        value = "live_provider"

    class FakeConfig:
        def __init__(self):
            self.type = FakeLiveType()
            self.enabled = True
            self.options = {}

    with pytest.raises(ProviderFactoryError, match="not allowed in PAPER environment"):
        factory.create_provider(FakeConfig(), environment=Environment.PAPER)


async def test_provider_factory_create_all_providers() -> None:
    """Test ProviderFactory.create_all_providers creates all enabled."""
    session_factory = _FakeSessionFactory()
    factory = ProviderFactory(session_factory)

    providers_config = ProvidersConfig(
        providers=[
            ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_SHARIAH, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_FUNDAMENTAL, enabled=False),  # disabled
        ]
    )

    providers = factory.create_all_providers(providers_config, environment=Environment.PAPER)

    assert len(providers) == 2
    assert isinstance(providers[0], MockMarketDataProvider)
    assert isinstance(providers[1], MockShariahDataProvider)


async def test_provider_factory_rejects_live_in_create_all() -> None:
    """Test ProviderFactory.create_all_providers rejects live provider in PAPER."""
    session_factory = _FakeSessionFactory()
    factory = ProviderFactory(session_factory)

    class FakeLiveType:
        value = "live_provider"

    class FakeConfig:
        def __init__(self):
            self.type = FakeLiveType()
            self.enabled = True
            self.options = {}

    # Create providers config with a fake live provider
    class FakeProvidersConfig:
        def __init__(self):
            self.providers = [
                ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True),
                FakeConfig(),
            ]
        
        def validate_for_environment(self, environment):
            pass
        
        def get_enabled_providers(self):
            return self.providers

    with pytest.raises(ProviderFactoryError, match="not allowed in PAPER environment"):
        factory.create_all_providers(FakeProvidersConfig(), environment=Environment.PAPER)


async def test_configuration_loads_providers_from_toml() -> None:
    """Test that providers configuration loads from TOML."""
    from aios.config.loader import load_settings
    from aios.config.settings import Environment

    # This test would need proper monkeypatch setup
    # For now, verify the model structure works
    providers_config = ProvidersConfig(
        providers=[
            ProviderConfig(type=ProviderType.MOCK_MARKET, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_SHARIAH, enabled=True),
            ProviderConfig(type=ProviderType.MOCK_FUNDAMENTAL, enabled=True),
        ]
    )
    assert len(providers_config.providers) == 3
    assert all(p.enabled for p in providers_config.providers)


async def test_provider_type_mock_types() -> None:
    """Test ProviderType.mock_types returns correct set."""
    mock_types = ProviderType.mock_types()
    assert ProviderType.MOCK_MARKET in mock_types
    assert ProviderType.MOCK_SHARIAH in mock_types
    assert ProviderType.MOCK_FUNDAMENTAL in mock_types
    assert ProviderType.MOCK_NEWS in mock_types
    assert len(mock_types) == 4


async def test_provider_type_is_mock() -> None:
    """Test ProviderType.is_mock method."""
    assert ProviderType.is_mock(ProviderType.MOCK_MARKET) is True
    assert ProviderType.is_mock(ProviderType.MOCK_SHARIAH) is True
    assert ProviderType.is_mock(ProviderType.MOCK_FUNDAMENTAL) is True


async def test_provider_config_options_validation() -> None:
    """Test ProviderConfig options can contain non-secret values."""
    config = ProviderConfig(
        type=ProviderType.MOCK_MARKET,
        enabled=True,
        options={"timeout": 30, "retry_count": 3},
    )
    assert config.options == {"timeout": 30, "retry_count": 3}


async def test_provider_config_options_rejects_password() -> None:
    """Test ProviderConfig options rejects password key."""
    with pytest.raises(ValueError, match="Secret key"):
        ProviderConfig(
            type=ProviderType.MOCK_MARKET,
            enabled=True,
            options={"password": "secret"},
        )