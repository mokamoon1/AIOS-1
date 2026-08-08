"""Audit event emission through the Event Bus (ADR-0010 section 5.5).

Audit logging records security and governance events: decisions, security
checks, permission violations, risk events. Audit events are emitted through
the Event Bus defined by ADR-0005 as event records with a unique Event ID,
and remain separate from normal application debugging logs.
"""

from __future__ import annotations

from typing import Any

from aios.events import Event, EventBus, EventPriority
from aios.logging.correlation import current_correlation


class AuditEventPublisher:
    """Publishes audit events onto the Event Bus (ADR-0010 section 5.5).

    Each audit event carries a unique Event ID (ADR-0005 section 5.3) and a
    payload describing the audited action so that governance events are
    traceable and explainable (ADR-0002, ADR-0005).
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self,
        *,
        action: str,
        subject: str,
        outcome: str,
        source: str,
        details: dict[str, Any] | None = None,
    ) -> Event:
        """Emit an audit event for the given action.

        Args:
            action: Audited action (e.g. ``decision.created``, ``permission.denied``).
            subject: Entity the action applies to (e.g. a component or agent).
            outcome: Result of the action (e.g. ``allowed``, ``denied``, ``approved``).
            source: Component that originated the event (ADR-0005).
            details: Optional structured context for the audit record.
        """
        correlation = current_correlation()
        payload: dict[str, Any] = {
            "action": action,
            "subject": subject,
            "outcome": outcome,
            "details": details or {},
        }
        if correlation.request_id:
            payload["request_id"] = correlation.request_id
        if correlation.trace_id:
            payload["trace_id"] = correlation.trace_id

        event = Event(
            source=source,
            event_type="AUDIT",
            priority=EventPriority.HIGH,
            payload=payload,
        )
        await self._bus.publish(event)
        return event
