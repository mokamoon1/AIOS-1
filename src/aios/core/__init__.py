"""AIOS Core Engine package (AIOS-104, ADR-0008).

The Core Engine coordinates platform startup and shutdown: configuration,
logging, database, Event Bus, Agent Manager, Engine Manager, and providers
(AIOS-104 section 4). It exposes lifecycle state, status/health reporting,
and clean shutdown.
"""

from __future__ import annotations

from aios.core.engine import CoreEngine, CoreState
from aios.core.exceptions import CoreBootstrapError, CoreError, CoreStateError

__all__ = [
    "CoreBootstrapError",
    "CoreEngine",
    "CoreError",
    "CoreState",
    "CoreStateError",
]
