"""AIOS unified error hierarchy (AIOS-104 section 7, AIOS-408 section 11).

The Core Engine must record problems, notify responsible components, and
prevent corrupted decisions when errors occur. A single root exception makes
error handling uniform across the platform while domain-specific subclasses
let components react to the failure categories defined in AIOS-104:
data, API/provider, agent, and database failures.
"""

from __future__ import annotations


class AiosError(Exception):
    """Base class for all AIOS errors (AIOS-104 section 7)."""


class ConfigurationError(AiosError):
    """Raised when runtime configuration cannot be resolved (ADR-0009)."""


class DatabaseError(AiosError):
    """Base class for all database layer errors (ADR-0001, ADR-0006)."""


class EventBusError(AiosError):
    """Base exception for Event Bus failures (ADR-0005 section 5.6)."""


class AgentError(AiosError):
    """Raised when an agent cannot execute or fails during processing.

    Covers the agent failure handling requirements of AIOS-604 section 15:
    the failure must be logged, the CIO Agent notified, and a safe retry or
    fail-safe path taken.
    """


class EngineError(AiosError):
    """Raised when an engine cannot initialize or fails during execution.

    Covers the engine failure handling requirements of AIOS-605 section 15:
    invalid input must be detected, failures reported to the Engine Manager,
    and corrupted results never propagated.
    """


class ProviderError(AiosError):
    """Raised when an external provider (market data, broker, Shariah) fails.

    Providers translate external responses into AIOS standard models
    (AIOS-603 section 6); provider failures must never corrupt those models.
    """


class WorkflowError(AiosError):
    """Raised when an investment workflow cannot proceed safely.

    Guards the workflow control responsibility of the Core Engine
    (AIOS-104 section 5.4): a workflow must stop rather than produce a
    corrupted decision.
    """


class SecurityError(AiosError):
    """Raised on security or permission violations (AIOS-408).

    Enforces least privilege, controlled access, and the trading safety
    controls defined in AIOS-408 sections 2 and 7.
    """


class DataError(AiosError):
    """Raised when data fails validation or integrity checks (AIOS-408 section 10)."""


class AnalysisError(AiosError):
    """Raised when an analysis computation fails or receives invalid input.

    Covers the analysis engine requirements of AIOS-305 and AIOS-405: engines
    must consume verified data, explain conclusions, and never propagate
    corrupted results.
    """
