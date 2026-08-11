"""Agent types and lifecycle states (AIOS-604 sections 3 and 4).

The canonical agent roster was confirmed from AIOS-401, AIOS-403, and
AIOS-604: CIO, Shariah, Market, Technical, Fundamental, Risk, and Portfolio
agents. Every agent follows the same lifecycle.
"""

from __future__ import annotations

from enum import Enum


class AgentType(str, Enum):
    """Canonical AIOS agent types (AIOS-401, AIOS-403, AIOS-604)."""

    CIO = "cio"
    SHARIAH = "shariah"
    MARKET = "market"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    RISK = "risk"
    PORTFOLIO = "portfolio"
    NEWS = "news"


class AgentState(str, Enum):
    """Lifecycle state of an agent (AIOS-604 section 4).

    Follows the documented lifecycle: Initialize -> Receive Context ->
    Process Information -> Generate Result -> Validate Output -> Publish
    Result -> Idle. Failed and Shutdown are terminal or quarantine states.
    """

    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    PROCESSING = "processing"
    IDLE = "idle"
    FAILED = "failed"
    SHUTDOWN = "shutdown"
