"""Data provider interface and Provider Manager (AIOS-603 section 6).

The Provider Module is responsible for communication with external
providers: market data, financial data, Shariah data, and broker APIs
(AIOS-603 section 6). Providers translate external responses into AIOS
standard models, and no module outside the Provider Module accesses a
provider directly (AIOS-603 section 6, AIOS-607).

Phase 1 does not connect any concrete provider: Alpaca and other brokers are
not part of the approved Core Engine bootstrap (AIOS-104 section 4). The
interface and registry are provided so that providers wire in without
changing the Core Engine.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from aios.providers.exceptions import ProviderNotFoundError, ProviderRegistrationError


@runtime_checkable
class DataProvider(Protocol):
    """Interface implemented by every AIOS data provider (AIOS-603 section 6).

    Providers connect and disconnect through the Core Engine lifecycle
    (AIOS-104 sections 4 and 5.2). They translate external responses into
    AIOS standard models; provider-specific logic never reaches engines
    (AIOS-605 section 13).
    """

    @property
    def name(self) -> str:
        """Return the stable provider name used for registration."""
        ...

    async def connect(self) -> None:
        """Establish the provider connection."""
        ...

    async def disconnect(self) -> None:
        """Close the provider connection and release resources."""
        ...

    def is_connected(self) -> bool:
        """Return whether the provider is currently connected."""
        ...


class ProviderManager:
    """Registry for data providers (AIOS-104 section 5.2).

    The Provider Manager registers providers, reports their status, and
    drives connect/disconnect through the Service Manager lifecycle. Phase 1
    registers no concrete providers; the registry is ready for future wiring.
    """

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._providers: dict[str, DataProvider] = {}
        self._logger = logger or logging.getLogger("aios.providers.manager")

    def register(self, provider: DataProvider) -> None:
        """Register ``provider`` by its name (AIOS-104 section 5.2)."""
        if provider.name in self._providers:
            raise ProviderRegistrationError(f"Provider {provider.name!r} is already registered")
        self._providers[provider.name] = provider
        self._logger.info("Registered provider %s", provider.name)

    def unregister(self, name: str) -> None:
        """Remove ``name`` from the registry."""
        if name not in self._providers:
            raise ProviderNotFoundError(f"No registered provider with name {name!r}")
        del self._providers[name]
        self._logger.info("Unregistered provider %s", name)

    def get(self, name: str) -> DataProvider:
        """Return the registered provider named ``name``."""
        if name not in self._providers:
            raise ProviderNotFoundError(f"No registered provider with name {name!r}")
        return self._providers[name]

    def list_providers(self) -> list[DataProvider]:
        """Return all registered providers in registration order."""
        return list(self._providers.values())

    def status(self) -> dict[str, bool]:
        """Return a map of provider name -> connection state."""
        return {name: provider.is_connected() for name, provider in self._providers.items()}

    async def connect_all(self) -> None:
        """Connect every registered provider (AIOS-104 section 4)."""
        for provider in self.list_providers():
            await provider.connect()
            self._logger.info("Connected provider %s", provider.name)

    async def disconnect_all(self) -> None:
        """Disconnect every registered provider."""
        for provider in self.list_providers():
            await provider.disconnect()
            self._logger.info("Disconnected provider %s", provider.name)
