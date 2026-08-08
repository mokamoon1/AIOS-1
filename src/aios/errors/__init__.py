"""AIOS error handling framework (AIOS-104 section 7, AIOS-408 section 11).

Provides:
    - A unified exception hierarchy rooted at ``AiosError``.
    - Error event publication through the Event Bus so failures notify
      responsible components (monitoring, CIO Agent, risk controls).
    - Safe-handling helpers that record failures, notify the Event Bus, and
      prevent corrupted decisions.
"""

from __future__ import annotations

from aios.errors.exceptions import (
    AgentError,
    AiosError,
    AnalysisError,
    ConfigurationError,
    DatabaseError,
    DataError,
    EngineError,
    EventBusError,
    ProviderError,
    SecurityError,
    WorkflowError,
)
from aios.errors.handling import capture_error, safe_call, safe_call_async
from aios.errors.publisher import ErrorEventPublisher

__all__ = [
    "AgentError",
    "AiosError",
    "AnalysisError",
    "ConfigurationError",
    "DataError",
    "DatabaseError",
    "EngineError",
    "ErrorEventPublisher",
    "EventBusError",
    "ProviderError",
    "SecurityError",
    "WorkflowError",
    "capture_error",
    "safe_call",
    "safe_call_async",
]
