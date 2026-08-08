"""Engine types and lifecycle states (AIOS-605 sections 3 and 4).

The canonical Phase 1 engine roster is defined in AIOS-605 section 3:
Market, Technical, Fundamental, Risk, Decision, and Signal engines. Every
engine follows the same lifecycle.
"""

from __future__ import annotations

from enum import Enum


class EngineType(str, Enum):
    """Canonical AIOS engine types (AIOS-605 section 3)."""

    MARKET = "market"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    RISK = "risk"
    DECISION = "decision"
    SIGNAL = "signal"


class EngineState(str, Enum):
    """Lifecycle state of an engine (AIOS-605 section 4).

    Follows the documented lifecycle: Initialize -> Load Data -> Validate
    Input -> Execute Analysis -> Generate Results -> Validate Results ->
    Publish Output. Failed and Shutdown are terminal or quarantine states.
    """

    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    PROCESSING = "processing"
    IDLE = "idle"
    FAILED = "failed"
    SHUTDOWN = "shutdown"
