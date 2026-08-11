"""Emergency stop / kill switch (Phase 9.6)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from threading import Lock

from aios.config import load_settings
from aios.monitoring.event_log import (
    EVENT_EMERGENCY_CLEAR,
    EVENT_EMERGENCY_STOP,
    EventLog,
)


class StopReason(str, Enum):
    """Reason for emergency stop."""
    MANUAL = "manual"
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded"
    SHARIAH_VIOLATION = "shariah_violation"
    SYSTEM_ERROR = "system_error"
    MANUAL_OVERRIDE = "manual_override"


@dataclass
class StopEvent:
    """Record of a stop event."""
    reason: StopReason
    triggered_by: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class EmergencyStopManager:
    """Global emergency stop / kill switch (Phase 9.6).
    
    Provides a global trading halt mechanism that can be triggered manually
    or automatically by risk limits, Shariah violations, or system errors.
    Once triggered, all trading activity is halted until explicitly acknowledged
    and cleared by authorized personnel.
    """

    def __init__(
        self,
        settings: Any | None = None,
        logger: logging.Logger | None = None,
        *,
        event_log: EventLog | None = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._logger = logger or logging.getLogger("aios.emergency_stop")
        self._event_log = event_log or EventLog()
        self._lock = Lock()
        self._is_stopped = False
        self._stop_event: StopEvent | None = None
        self._callbacks: list[Callable[[StopEvent], None]] = []
        self._stop_history: list[StopEvent] = []

    @property
    def event_log(self) -> EventLog:
        """Return the underlying audit event log."""
        return self._event_log

    def register_callback(self, callback: Callable[[StopEvent], None]) -> None:
        """Register a callback to be notified when stop is triggered."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[StopEvent], None]) -> bool:
        """Remove a registered callback."""
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    @property
    def is_stopped(self) -> bool:
        """Check if emergency stop is active."""
        with self._lock:
            return self._is_stopped

    @property
    def current_stop_event(self) -> StopEvent | None:
        """Get the current stop event if any."""
        with self._lock:
            return self._stop_event

    def trigger_stop(
        self,
        reason: StopReason,
        triggered_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> StopEvent:
        """Trigger emergency stop.
        
        Args:
            reason: Reason for the emergency stop
            triggered_by: Identifier of who/what triggered the stop
            metadata: Additional metadata about the stop
            
        Returns:
            The stop event that was created
        """
        with self._lock:
            if self._is_stopped:
                self._logger.warning("Emergency stop already active")
                return self._stop_event

            self._is_stopped = True
            stop_event = StopEvent(
                reason=reason,
                triggered_by=triggered_by,
                timestamp=datetime.now(timezone.utc),
                metadata=metadata or {},
            )
            self._stop_event = stop_event
            self._stop_history.append(stop_event)

            self._logger.critical(
                "EMERGENCY STOP TRIGGERED: %s by %s - %s",
                reason.value,
                triggered_by,
                metadata or {},
            )
            self._event_log.record(
                EVENT_EMERGENCY_STOP,
                "emergency_stop_manager",
                payload={
                    "reason": reason.value,
                    "triggered_by": triggered_by,
                    "metadata": metadata or {},
                },
                at=stop_event.timestamp.replace(tzinfo=None),
            )
        
        # Notify callbacks outside of lock
        for callback in self._callbacks:
            try:
                callback(self._stop_event)
            except Exception as exc:
                self._logger.exception("Error in stop callback: %s", exc)
        
        return self._stop_event

    def acknowledge_stop(self, acknowledged_by: str) -> bool:
        """Acknowledge the emergency stop.
        
        Args:
            acknowledged_by: Identifier of who acknowledged the stop
            
        Returns:
            True if stop was acknowledged, False if no active stop
        """
        with self._lock:
            if not self._is_stopped or self._stop_event is None:
                return False
            
            if self._stop_event.acknowledged:
                self._logger.warning("Stop already acknowledged by %s", 
                                   self._stop_event.acknowledged_by)
                return False
            
            self._stop_event.acknowledged = True
            self._stop_event.acknowledged_by = acknowledged_by
            self._stop_event.acknowledged_at = datetime.now(timezone.utc)
            
            self._logger.info("Emergency stop acknowledged by %s", acknowledged_by)
            return True

    def clear_stop(self, cleared_by: str) -> bool:
        """Clear the emergency stop after acknowledgment.
        
        Args:
            cleared_by: Identifier of who cleared the stop
            
        Returns:
            True if stop was cleared, False if no active stop or not acknowledged
        """
        with self._lock:
            if not self._is_stopped or self._stop_event is None:
                return False
            
            if not self._stop_event.acknowledged:
                self._logger.warning("Cannot clear unacknowledged stop")
                return False
            
            self._is_stopped = False
            cleared_event = self._stop_event
            self._stop_event = None

            self._logger.info(
                "Emergency stop cleared by %s (was triggered by %s for %s)",
                cleared_by,
                cleared_event.triggered_by,
                cleared_event.reason.value,
            )
            self._event_log.record(
                EVENT_EMERGENCY_CLEAR,
                "emergency_stop_manager",
                payload={
                    "cleared_by": cleared_by,
                    "reason": cleared_event.reason.value,
                    "triggered_by": cleared_event.triggered_by,
                },
                at=datetime.now(timezone.utc),
            )
            return True

    def is_operation_allowed(self) -> bool:
        """Check if trading operations are allowed.
        
        Returns:
            True if operations are allowed, False if emergency stop is active
        """
        return not self.is_stopped

    def get_status(self) -> dict[str, Any]:
        """Get current emergency stop status."""
        with self._lock:
            return {
                "is_stopped": self._is_stopped,
                "current_stop": {
                    "reason": self._stop_event.reason.value if self._stop_event else None,
                    "triggered_by": self._stop_event.triggered_by if self._stop_event else None,
                    "timestamp": self._stop_event.timestamp.isoformat() if self._stop_event else None,
                    "acknowledged": self._stop_event.acknowledged if self._stop_event else None,
                    "acknowledged_by": self._stop_event.acknowledged_by if self._stop_event else None,
                } if self._stop_event else None,
                "total_stops": len(self._stop_history),
            }


def create_emergency_stop_manager(
    settings: Any | None = None,
    logger: logging.Logger | None = None,
    *,
    event_log: EventLog | None = None,
) -> EmergencyStopManager:
    """Factory function to create an EmergencyStopManager."""
    return EmergencyStopManager(settings, logger, event_log=event_log)