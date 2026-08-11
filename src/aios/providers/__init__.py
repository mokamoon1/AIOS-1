"""AIOS data provider package (AIOS-603 section 6).

Provides the ``DataProvider`` interface, the ``ProviderManager`` registry,
the ``ProviderFactory``, the ``DataProviderAdapter`` interface, concrete
adapter implementations, and the typed data provider interfaces used by the
Data Layer. Providers translate external responses into AIOS standard models
(AIOS-607).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aios.providers.adapter import (
    BatchIngestionResult,
    DataProviderAdapter,
    FundamentalDataAdapter,
    IngestionResult,
    IngestionResultType,
    MarketDataAdapter,
    NewsDataAdapter,
    ShariahDataAdapter,
)
from aios.providers.base import DataProvider, ProviderManager
from aios.providers.exceptions import ProviderNotFoundError, ProviderRegistrationError
from aios.providers.factory import ProviderFactory, ProviderFactoryError
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
from aios.providers.provider_adapters import (
    FundamentalDataProviderAdapter,
    MarketDataProviderAdapter,
    NewsDataProviderAdapter,
    ShariahDataProviderAdapter,
)
from aios.providers.registry import (
    ProviderConfig,
    ProviderType,
    ProvidersConfig,
)

__all__ = [
    "BatchIngestionResult",
    "DataProvider",
    "DataProviderAdapter",
    "FundamentalDataAdapter",
    "FundamentalDataProvider",
    "FundamentalDataProviderAdapter",
    "IngestionResult",
    "IngestionResultType",
    "MarketDataAdapter",
    "MarketDataProvider",
    "MarketDataProviderAdapter",
    "MockFundamentalDataProvider",
    "MockMarketDataProvider",
    "MockNewsDataProvider",
    "MockShariahDataProvider",
    "NewsDataAdapter",
    "NewsDataProvider",
    "ProviderConfig",
    "ProviderFactory",
    "ProviderFactoryError",
    "ProviderManager",
    "ProviderNotFoundError",
    "ProviderRegistrationError",
    "ProviderType",
    "ProvidersConfig",
    "ShariahDataAdapter",
    "ShariahDataProvider",
    "ShariahDataProviderAdapter",
]
