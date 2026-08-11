"""Provider factory for creating data providers from configuration (AIOS-603 section 6).

Creates provider instances based on configuration, injecting required
repository dependencies. Only mock providers are supported in Phase 7.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aios.database.repositories import (
    CompanyRepository,
    MarketRepository,
    ShariahRepository,
)
from aios.providers.base import DataProvider
from aios.providers.interfaces import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
    ShariahDataProvider,
)
from aios.providers.mock import (
    MockFundamentalDataProvider,
    MockMarketDataProvider,
    MockNewsDataProvider,
    MockShariahDataProvider,
)
from aios.providers.registry import ProviderConfig, ProviderType, ProvidersConfig

if TYPE_CHECKING:
    from aios.config.settings import Environment


class ProviderFactoryError(Exception):
    """Raised when provider creation fails."""


class ProviderFactory:
    """Factory for creating data provider instances from configuration.

    The factory requires a session factory to create repository instances
    that are injected into the providers. This maintains the dependency
    inversion principle: providers depend on repository interfaces, not
    concrete database implementations.
    """

    def __init__(
        self,
        session_factory: Any,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger or logging.getLogger("aios.providers.factory")

    def create_provider(
        self,
        config: ProviderConfig,
        *,
        environment: "Environment",
    ) -> DataProvider:
        """Create a provider instance from configuration.

        Args:
            config: Provider configuration specifying type and options.
            environment: Current runtime environment for validation.

        Returns:
            A provider instance implementing the appropriate protocol.

        Raises:
            ProviderFactoryError: If the provider type is unknown, not allowed
                in the current environment, or creation fails.
        """
        # Import at runtime to avoid circular imports
        from aios.config.settings import Environment

        # Validate provider is allowed in this environment
        if environment is Environment.PAPER and not ProviderType.is_mock(config.type):
            raise ProviderFactoryError(
                f"Provider type {config.type.value!r} is not allowed in PAPER environment. "
                f"Only mock providers are permitted."
            )

        try:
            if config.type is ProviderType.MOCK_MARKET:
                return self._create_mock_market(config)
            elif config.type is ProviderType.MOCK_SHARIAH:
                return self._create_mock_shariah(config)
            elif config.type is ProviderType.MOCK_FUNDAMENTAL:
                return self._create_mock_fundamental(config)
            elif config.type is ProviderType.MOCK_NEWS:
                return self._create_mock_news(config)
            else:
                raise ProviderFactoryError(
                    f"Unknown provider type: {config.type.value!r}. "
                    f"Supported types: {[t.value for t in ProviderType]}"
                )
        except Exception as exc:
            raise ProviderFactoryError(
                f"Failed to create provider {config.type.value!r}: {exc}"
            ) from exc

    def create_all_providers(
        self,
        providers_config: ProvidersConfig,
        *,
        environment: "Environment",
    ) -> list[DataProvider]:
        """Create all enabled providers from configuration.

        Args:
            providers_config: Complete providers configuration.
            environment: Current runtime environment for validation.

        Returns:
            List of created provider instances in configuration order.
        """
        providers_config.validate_for_environment(environment)
        enabled = providers_config.get_enabled_providers()
        self._logger.info("Creating %d enabled providers for %s environment", len(enabled), environment.value)

        providers: list[DataProvider] = []
        for config in enabled:
            provider = self.create_provider(config, environment=environment)
            providers.append(provider)
            self._logger.info("Created provider: %s", config.type.value)

        return providers

    def _create_mock_market(self, config: ProviderConfig) -> MockMarketDataProvider:
        """Create a MockMarketDataProvider with required dependencies."""
        market_repository = MarketRepository(self._session_factory)
        return MockMarketDataProvider(market_repository)

    def _create_mock_shariah(self, config: ProviderConfig) -> MockShariahDataProvider:
        """Create a MockShariahDataProvider with required dependencies."""
        shariah_repository = ShariahRepository(self._session_factory)
        return MockShariahDataProvider(shariah_repository)

    def _create_mock_fundamental(self, config: ProviderConfig) -> MockFundamentalDataProvider:
        """Create a MockFundamentalDataProvider with required dependencies."""
        company_repository = CompanyRepository(self._session_factory)
        return MockFundamentalDataProvider(company_repository)

    def _create_mock_news(self, config: ProviderConfig) -> MockNewsDataProvider:
        """Create a MockNewsDataProvider with required dependencies."""
        return MockNewsDataProvider()