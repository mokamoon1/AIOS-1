"""AIOS data provider package (AIOS-603 section 6).

Provides the ``DataProvider`` interface, the ``ProviderManager`` registry,
the ``ProviderFactory``, and the typed data provider interfaces used by the
Data Layer. Providers translate external responses into AIOS standard models
(AIOS-607).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aios.providers.base import DataProvider, ProviderManager
from aios.providers.exceptions import ProviderNotFoundError, ProviderRegistrationError
from aios.providers.factory import ProviderFactory, ProviderFactoryError
from aios.providers.interfaces import (
    FundamentalDataProvider,
    MarketDataProvider,
    ShariahDataProvider,
)
from aios.providers.mock import (
    MockFundamentalDataProvider,
    MockMarketDataProvider,
    MockShariahDataProvider,
)
from aios.providers.registry import (
    ProviderConfig,
    ProviderType,
    ProvidersConfig,
)

__all__ = [
    "DataProvider",
    "FundamentalDataProvider",
    "MarketDataProvider",
    "MockFundamentalDataProvider",
    "MockMarketDataProvider",
    "MockShariahDataProvider",
    "ProviderConfig",
    "ProviderFactory",
    "ProviderFactoryError",
    "ProviderManager",
    "ProviderNotFoundError",
    "ProviderRegistrationError",
    "ProviderType",
    "ProvidersConfig",
    "ShariahDataProvider",
]
