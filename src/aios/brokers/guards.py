"""Order execution guards (Phase 9.6, P0-2 / P0-5).

The emergency stop (kill switch) and the market-session guard are enforced on
the paper order path through a small :class:`GuardChain`. Every guard exposes
``block_reason(order)`` and returns ``None`` when the operation is allowed or
a human-readable reason when it must be rejected. The chain short-circuits on
the first block so the reason surfaced to the operator is the earliest gate
that failed.

Guards never bypass existing Shariah, risk, or approval gates: they run
*in addition* to the decision-approval chain in ``BrokerService``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from aios.brokers.exceptions import TradeBlockedError


@runtime_checkable
class ExecutionGuard(Protocol):
    """A gate over order submission/execution returning a block reason."""

    def block_reason(self, order: Any) -> str | None: ...


class EmergencyStopGuard:
    """Rejects every order while the emergency stop / kill switch is active.

    ``stop_manager`` exposes ``is_stopped`` (bool) and, optionally,
    ``current_stop_event``; the protocol is structural so any compatible
    stop manager can be supplied without a hard dependency.
    """

    def __init__(self, stop_manager: Any, *, logger: logging.Logger | None = None) -> None:
        self._stop_manager = stop_manager
        self._logger = logger or logging.getLogger("aios.brokers.guards")

    def block_reason(self, order: Any) -> str | None:
        if not self._stop_manager.is_stopped:
            return None
        event = getattr(self._stop_manager, "current_stop_event", None)
        if event is not None and getattr(event, "reason", None) is not None:
            return (
                f"emergency stop active ({event.reason.value}); "
                f"triggered by {event.triggered_by}"
            )
        return "emergency stop active; trading is halted"


class MarketSessionGuardAdapter:
    """Adapts :class:`MarketSessionGuard` to the execution-guard protocol."""

    def __init__(self, session_guard: Any, *, logger: logging.Logger | None = None) -> None:
        self._session_guard = session_guard
        self._logger = logger or logging.getLogger("aios.brokers.guards")

    def block_reason(self, order: Any) -> str | None:
        return self._session_guard.closed_reason()


class GuardChain:
    """Applies a sequence of guards; the first block reason wins.

    With no guards configured the chain always allows the operation, which
    preserves the behavior of environments where the Phase 9.6 controls are
    disabled by configuration.
    """

    def __init__(
        self,
        guards: list[ExecutionGuard] | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._guards: list[ExecutionGuard] = list(guards or [])
        self._logger = logger or logging.getLogger("aios.brokers.guards")

    def add_guard(self, guard: ExecutionGuard) -> None:
        """Append a guard to the chain."""
        self._guards.append(guard)

    def block_reason(self, order: Any) -> str | None:
        """Return the first block reason among the configured guards."""
        for guard in self._guards:
            try:
                reason = guard.block_reason(order)
            except Exception as exc:  # noqa: BLE001 - a failing guard blocks safely
                self._logger.exception("Guard %s failed: %s", type(guard).__name__, exc)
                return f"execution guard {type(guard).__name__} failed: {exc}"
            if reason:
                return reason
        return None

    def assert_allows(self, order: Any, *, operation: str = "order submission") -> None:
        """Raise :class:`TradeBlockedError` when a guard blocks the order."""
        reason = self.block_reason(order)
        if reason is None:
            return
        code = "emergency_stop" if "emergency stop" in reason else "market_closed"
        raise TradeBlockedError(
            f"{operation} blocked: {reason}",
            code=code,
            reason=reason,
        )
