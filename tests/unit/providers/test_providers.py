"""Tests for the data provider interface and Provider Manager (AIOS-603
section 6, AIOS-104 section 5.2)."""

from __future__ import annotations

import pytest

from aios.providers.base import ProviderManager
from aios.providers.exceptions import ProviderNotFoundError, ProviderRegistrationError


class FakeProvider:
    """Minimal provider implementing the ``DataProvider`` protocol."""

    def __init__(self, name: str = "fake") -> None:
        self._name = name
        self._connected = False

    @property
    def name(self) -> str:
        return self._name

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected


async def test_register_and_get() -> None:
    manager = ProviderManager()
    provider = FakeProvider()
    manager.register(provider)
    assert manager.get("fake") is provider


async def test_duplicate_registration_raises() -> None:
    manager = ProviderManager()
    provider = FakeProvider()
    manager.register(provider)
    with pytest.raises(ProviderRegistrationError):
        manager.register(FakeProvider(name="fake"))


async def test_get_unknown_raises() -> None:
    manager = ProviderManager()
    with pytest.raises(ProviderNotFoundError):
        manager.get("missing")


async def test_unregister_removes_provider() -> None:
    manager = ProviderManager()
    manager.register(FakeProvider())
    manager.unregister("fake")
    with pytest.raises(ProviderNotFoundError):
        manager.get("fake")


async def test_unregister_unknown_raises() -> None:
    manager = ProviderManager()
    with pytest.raises(ProviderNotFoundError):
        manager.unregister("missing")


async def test_list_providers_preserves_order() -> None:
    manager = ProviderManager()
    first = FakeProvider(name="a")
    second = FakeProvider(name="b")
    manager.register(first)
    manager.register(second)
    assert manager.list_providers() == [first, second]


async def test_status_reports_connection_state() -> None:
    manager = ProviderManager()
    manager.register(FakeProvider())
    assert manager.status() == {"fake": False}


async def test_connect_all_and_disconnect_all() -> None:
    manager = ProviderManager()
    first = FakeProvider(name="a")
    second = FakeProvider(name="b")
    manager.register(first)
    manager.register(second)
    await manager.connect_all()
    assert first.is_connected()
    assert second.is_connected()
    assert manager.status() == {"a": True, "b": True}
    await manager.disconnect_all()
    assert not first.is_connected()
    assert not second.is_connected()
    assert manager.status() == {"a": False, "b": False}
