"""Role-based permission model (AIOS-408 sections 2 and 8).

AIOS follows least privilege and controlled access. The roles and their
permissions are taken strictly from AIOS-408 section 8:

* Administrator: configure system, manage connections.
* Analyst: view analysis, review reports.
* Trading Module: send approved paper orders only.

The framework denies access to any role that lacks a permission.
"""

from __future__ import annotations

from enum import Enum

from aios.errors import SecurityError


class Permission(str, Enum):
    """Granular permissions defined in AIOS-408 section 8."""

    CONFIGURE_SYSTEM = "configure_system"
    MANAGE_CONNECTIONS = "manage_connections"
    VIEW_ANALYSIS = "view_analysis"
    REVIEW_REPORTS = "review_reports"
    SUBMIT_PAPER_ORDERS = "submit_paper_orders"


class Role(str, Enum):
    """System roles defined in AIOS-408 section 8."""

    ADMINISTRATOR = "administrator"
    ANALYST = "analyst"
    TRADING = "trading_module"


_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMINISTRATOR: frozenset(
        {
            Permission.CONFIGURE_SYSTEM,
            Permission.MANAGE_CONNECTIONS,
        }
    ),
    Role.ANALYST: frozenset(
        {
            Permission.VIEW_ANALYSIS,
            Permission.REVIEW_REPORTS,
        }
    ),
    Role.TRADING: frozenset(
        {
            Permission.SUBMIT_PAPER_ORDERS,
        }
    ),
}


def permissions_for(role: Role) -> frozenset[Permission]:
    """Return the permission set granted to ``role`` (least privilege)."""
    return _ROLE_PERMISSIONS[role]


def has_permission(role: Role, permission: Permission) -> bool:
    """Return whether ``role`` holds ``permission``."""
    return permission in _ROLE_PERMISSIONS[role]


def require_permission(role: Role, permission: Permission) -> None:
    """Raise :class:`SecurityError` unless ``role`` holds ``permission``.

    Enforces the controlled-access requirement of AIOS-408 section 2.
    """
    if not has_permission(role, permission):
        raise SecurityError(f"Role {role.value!r} lacks required permission {permission.value!r}")
