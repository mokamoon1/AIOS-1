"""AIOS agent framework package (AIOS-604, ADR-0002, ADR-0004).

The framework provides:

* The standard agent interface and lifecycle (``Agent``).
* The Phase 1 core roster of seven agents (CIO, Shariah, Market, Technical,
  Fundamental, Risk, Portfolio).
* Role-based permissions from AIOS-408 section 8.
* The Agent Manager registry (AIOS-104 section 5.3).
* Structured messages and Event Bus integration (AIOS-604 section 14).
* CIO authority enforcement (AIOS-403 section 14, ADR-0002).
"""

from __future__ import annotations

from aios.agents.base import Agent
from aios.agents.exceptions import (
    AgentNotFoundError,
    AgentRegistrationError,
    AgentStateError,
)
from aios.agents.manager import AgentManager
from aios.agents.messages import AgentContext, AgentMessage, AgentResult, MessageStatus
from aios.agents.permissions import (
    Permission,
    Role,
    has_permission,
    permissions_for,
    require_permission,
)
from aios.agents.roster import (
    AGENT_CLASSES,
    CIOAgent,
    FundamentalAgent,
    MarketAgent,
    PortfolioAgent,
    RiskAgent,
    ShariahAgent,
    TechnicalAgent,
    create_agent,
    require_cio_authority,
)
from aios.agents.types import AgentState, AgentType

__all__ = [
    "AGENT_CLASSES",
    "Agent",
    "AgentContext",
    "AgentManager",
    "AgentMessage",
    "AgentNotFoundError",
    "AgentRegistrationError",
    "AgentResult",
    "AgentState",
    "AgentStateError",
    "AgentType",
    "CIOAgent",
    "FundamentalAgent",
    "MarketAgent",
    "MessageStatus",
    "Permission",
    "PortfolioAgent",
    "RiskAgent",
    "Role",
    "ShariahAgent",
    "TechnicalAgent",
    "create_agent",
    "has_permission",
    "permissions_for",
    "require_cio_authority",
    "require_permission",
]
