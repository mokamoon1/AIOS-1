"""AIOS engine framework package (AIOS-605, ADR-0004).

The framework provides:

* The standard engine interface and lifecycle (``Engine``).
* The Phase 1 engine roster of six engines (Market, Technical, Fundamental,
  Risk, Decision, Signal).
* The Engine Manager registry and dependency-aware execution order
  (AIOS-605 section 3).
* Standardized engine messages with the AIOS-605 section 12 contract.
* Decision Engine authority enforcement (AIOS-605 section 11).
"""

from __future__ import annotations

from aios.engines.base import Engine
from aios.engines.exceptions import (
    EngineDependencyError,
    EngineNotFoundError,
    EngineRegistrationError,
    EngineStateError,
    EngineValidationError,
)
from aios.engines.manager import EngineManager
from aios.engines.messages import EngineInput, EngineOutput
from aios.engines.roster import (
    ENGINE_CLASSES,
    DecisionEngine,
    FundamentalEngine,
    MarketEngine,
    RiskEngine,
    SignalEngine,
    TechnicalEngine,
    create_engine,
    require_decision_authority,
)
from aios.engines.types import EngineState, EngineType

__all__ = [
    "ENGINE_CLASSES",
    "DecisionEngine",
    "Engine",
    "EngineDependencyError",
    "EngineInput",
    "EngineManager",
    "EngineNotFoundError",
    "EngineOutput",
    "EngineRegistrationError",
    "EngineState",
    "EngineStateError",
    "EngineType",
    "EngineValidationError",
    "FundamentalEngine",
    "MarketEngine",
    "RiskEngine",
    "SignalEngine",
    "TechnicalEngine",
    "create_engine",
    "require_decision_authority",
]
