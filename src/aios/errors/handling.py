"""Safe error handling helpers (AIOS-104 section 7, AIOS-408 section 11).

Failures must be recorded, must notify responsible components, and must
never corrupt decisions. These helpers centralize logging and Event Bus
notification so component code stays focused on its task. Because the Event
Bus is asynchronous (ADR-0005), notification-capable helpers are async.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from aios.errors.publisher import ErrorEventPublisher

T = TypeVar("T")

_FALLBACK_SOURCE = "core-engine"


async def _notify(
    *,
    logger: logging.Logger,
    component: str,
    source: str | None,
    publisher: ErrorEventPublisher | None,
    exc: Exception,
) -> None:
    logger.exception("Component failure in %s: %s", component, exc)
    if publisher is not None:
        await publisher.publish(
            source=source or _FALLBACK_SOURCE,
            component=component,
            error_type=type(exc).__name__,
            message=str(exc),
        )


@asynccontextmanager
async def capture_error(
    *,
    logger: logging.Logger,
    component: str,
    source: str | None = None,
    publisher: ErrorEventPublisher | None = None,
    re_raise: bool = True,
):
    """Run an async block, logging and notifying on failure (AIOS-104 §7).

    On any exception the problem is recorded through the logger and, when a
    publisher is provided, an ERROR event is emitted for responsible
    components to react. Sensitive data is masked by the logging layer and
    the error publisher (AIOS-408 section 11).

    Args:
        logger: Logger used to record the failure.
        component: The component that failed.
        source: Event source (defaults to ``core-engine``).
        publisher: Optional publisher used to notify the Event Bus.
        re_raise: Whether the exception is re-raised after being handled.
            Set to ``False`` for non-critical operations where execution may
            continue safely (AIOS-604 section 15).
    """
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - intentional fail-safe boundary
        await _notify(
            logger=logger,
            component=component,
            source=source,
            publisher=publisher,
            exc=exc,
        )
        if re_raise:
            raise


async def safe_call_async(
    callable_: Callable[[], Awaitable[T]],
    *,
    logger: logging.Logger,
    component: str,
    source: str | None = None,
    publisher: ErrorEventPublisher | None = None,
    default: Any = None,
) -> T:
    """Await ``callable_`` and return ``default`` on failure.

    Use for optional, non-critical operations: the failure is logged and
    reported, and execution continues with ``default`` instead of corrupting
    the decision flow (AIOS-104 section 7, AIOS-604 section 15).
    """
    try:
        return await callable_()
    except Exception as exc:  # noqa: BLE001 - intentional fail-safe boundary
        await _notify(
            logger=logger,
            component=component,
            source=source,
            publisher=publisher,
            exc=exc,
        )
        return default


def safe_call(
    callable_: Callable[[], T],
    *,
    logger: logging.Logger,
    component: str,
    default: Any = None,
) -> T:
    """Invoke a synchronous ``callable_`` and return ``default`` on failure.

    The failure is recorded through the logger. Because the Event Bus is
    asynchronous, use :func:`safe_call_async` (or :func:`capture_error`) in
    async contexts when Event Bus notification is required.
    """
    try:
        return callable_()
    except Exception as exc:  # noqa: BLE001 - intentional fail-safe boundary
        logger.exception("Component failure in %s: %s", component, exc)
        return default
