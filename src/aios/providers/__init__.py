"""AIOS data provider package (AIOS-603 section 6).

Provides the ``DataProvider`` interface, the ``ProviderManager`` registry,
and the typed data provider interfaces used by the Data Layer. Providers
translate external responses into AIOS standard models (AIOS-607).
"""

from __future__ import annotations

from aios.providers.base import DataProvider, ProviderManager
from aios.providers.exceptions import ProviderNotFoundError, ProviderRegistrationError
from aios.providers.interfaces import (
    FundamentalDataProvider,
    MarketDataProvider,
    ShariahDataProvider,
)

__all__ = [
    "DataProvider",
    "FundamentalDataProvider",
    "MarketDataProvider",
    "ProviderManager",
    "ProviderNotFoundError",
    "ProviderRegistrationError",
    "ShariahDataProvider",
]
