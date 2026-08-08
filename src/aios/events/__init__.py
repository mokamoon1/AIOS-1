"""Internal Event Bus package (ADR-0005, ADR-0010).

The Event Bus is the only communication path between components
(ADR-0005 section 5.7). Audit events carried on the bus are recorded in the
Audit Log, separate from diagnostic logs (ADR-0010).
"""

from aios.events.bus import EventBus, InMemoryEventBus
from aios.events.event import Event, EventPriority, EventStatus
from aios.events.exceptions import EventBusError, EventValidationError
from aios.events.handlers import (
    AsyncEventHandler,
    EventHandler,
    EventHandlerCallable,
)
from aios.events.repository import EventRepository

__all__ = [
    "AsyncEventHandler",
    "Event",
    "EventBus",
    "EventBusError",
    "EventHandler",
    "EventHandlerCallable",
    "EventPriority",
    "EventRepository",
    "EventStatus",
    "EventValidationError",
    "InMemoryEventBus",
]
