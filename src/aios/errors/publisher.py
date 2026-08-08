"""Error event publication through the Event Bus (AIOS-104 section 7).

When the Core Engine or any component encounters a failure it must record
the problem and notify responsible components. Error events are published
through the Event Bus so subscribers (monitoring, the CIO Agent, risk
controls) can react without coupling components directly.
"""

from __future__ import annotations

from typing import Any

from aios.events import Event, EventBus, EventPriority
from aios.logging.masking import mask_sensitive


class ErrorEventPublisher:
    """Publishes ERROR events onto the Event Bus (AIOS-104 section 7).

    Messages are masked before publication so that errors never leak
    sensitive information (AIOS-408 section 11).
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self,
        *,
        source: str,
        component: str,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> Event:
        """Emit an ERROR event describing a component failure.

        Args:
            source: Component that originated the event (ADR-0005).
            component: The component that failed.
            error_type: Machine-readable failure category (e.g. exception
                class name).
            message: Human-readable description of the failure. Sensitive
                values are masked before publication.
            details: Optional structured failure context.
        """
        event = Event(
            source=source,
            event_type="ERROR",
            priority=EventPriority.HIGH,
            payload={
                "component": component,
                "error_type": error_type,
                "message": mask_sensitive(message),
                "details": details or {},
            },
        )
        await self._bus.publish(event)
        return event
