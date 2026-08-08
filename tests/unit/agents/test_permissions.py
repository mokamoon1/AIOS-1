"""Tests for role-based permissions (AIOS-408 sections 2 and 8)."""

from __future__ import annotations

import pytest

from aios.agents.permissions import (
    Permission,
    Role,
    has_permission,
    permissions_for,
    require_permission,
)
from aios.errors import SecurityError


def test_administrator_permissions() -> None:
    perms = permissions_for(Role.ADMINISTRATOR)
    assert Permission.CONFIGURE_SYSTEM in perms
    assert Permission.MANAGE_CONNECTIONS in perms
    assert Permission.VIEW_ANALYSIS not in perms
    assert Permission.SUBMIT_PAPER_ORDERS not in perms


def test_analyst_permissions() -> None:
    perms = permissions_for(Role.ANALYST)
    assert Permission.VIEW_ANALYSIS in perms
    assert Permission.REVIEW_REPORTS in perms
    assert Permission.CONFIGURE_SYSTEM not in perms


def test_trading_module_permissions() -> None:
    perms = permissions_for(Role.TRADING)
    assert Permission.SUBMIT_PAPER_ORDERS in perms
    assert Permission.VIEW_ANALYSIS not in perms
    assert Permission.CONFIGURE_SYSTEM not in perms


def test_has_permission() -> None:
    assert has_permission(Role.ANALYST, Permission.VIEW_ANALYSIS)
    assert not has_permission(Role.ANALYST, Permission.MANAGE_CONNECTIONS)


def test_require_permission_allows_granted() -> None:
    require_permission(Role.ANALYST, Permission.VIEW_ANALYSIS)


def test_require_permission_raises_for_denied() -> None:
    with pytest.raises(SecurityError):
        require_permission(Role.TRADING, Permission.VIEW_ANALYSIS)
