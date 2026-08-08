"""Operational health snapshot (AIOS-107 section 10, AIOS-807 section 7).

AIOS-107 section 10 requires monitoring of system health, data availability,
agent status, errors, and performance. AIOS-807 section 7 additionally lists
broker connectivity and provider status. This module derives a structured
:class:`HealthSnapshot` from the Core Engine status map and engine metrics;
it never fabricates availability and defines no alert thresholds, which the
approved documents leave to operational tooling (AIOS-705 section 13).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

_READY_STATE = "ready"


class HealthSnapshot(BaseModel):
    """Structured health report over the documented monitoring dimensions.

    Every field is derived from reported state rather than guessed: absent
    or unknown components produce ``False``/zero counts so the snapshot never
    overstates availability (AIOS-807 section 7).
    """

    environment: str | None = None
    state: str | None = None
    service_available: bool = False
    data_available: bool = False
    broker_connected: bool = False
    providers_connected: int = 0
    agent_loaded: int = 0
    agent_ready: int = 0
    engine_loaded: int = 0
    engine_ready: int = 0
    error_counts: dict[str, int] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)


class HealthMonitor:
    """Produces :class:`HealthSnapshot` reports from component state.

    ``snapshot`` accepts the Core Engine status map (``core.status()``) and,
    optionally, the list of engine metric maps (``engine.metrics()``) so
    performance and error dimensions are included when available (AIOS-605
    section 16). Callers may supply operational error counts recorded by
    their monitoring integration.
    """

    def snapshot(
        self,
        status: Mapping[str, Any],
        *,
        engine_metrics: Sequence[Mapping[str, Any]] | None = None,
        error_counts: Mapping[str, int] | None = None,
    ) -> HealthSnapshot:
        components = status.get("components")
        component_map = components if isinstance(components, Mapping) else {}

        agents = component_map.get("agents")
        agent_map = agents if isinstance(agents, Mapping) else {}
        engines = component_map.get("engines")
        engine_map = engines if isinstance(engines, Mapping) else {}

        providers = component_map.get("providers")
        providers_connected = 0
        if isinstance(providers, Mapping):
            # ProviderManager.status() returns {provider_name: is_connected_bool}
            # Count providers that are connected (True)
            providers_connected = sum(1 for v in providers.values() if v is True)

        engine_metrics_list = list(engine_metrics) if engine_metrics else []
        return HealthSnapshot(
            environment=_optional_str(status.get("environment")),
            state=_optional_str(status.get("state")),
            service_available=_optional_str(status.get("state")) == _READY_STATE,
            data_available=bool(component_map.get("database")),
            broker_connected=bool(component_map.get("broker")),
            providers_connected=providers_connected,
            agent_loaded=_count(agent_map.get("loaded")),
            agent_ready=_count(agent_map.get("ready")),
            engine_loaded=_count(engine_map.get("loaded")),
            engine_ready=_count(engine_map.get("ready")),
            error_counts=dict(error_counts) if error_counts else {},
            performance=_aggregate_performance(engine_metrics_list),
        )


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _count(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _aggregate_performance(metrics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate engine metrics (AIOS-705 section 11, AIOS-605 section 16).

    Execution count, failure count, and total duration are summed across
    engines; per-engine records are preserved so trend analysis remains
    possible (AIOS-705 section 12).
    """
    total_executions = 0
    total_failures = 0
    total_duration = 0.0
    for metric in metrics:
        total_executions += (
            metric.get("execution_count", 0)
            if isinstance(metric.get("execution_count"), int)
            else 0
        )
        total_failures += (
            metric.get("failure_count", 0) if isinstance(metric.get("failure_count"), int) else 0
        )
        duration = metric.get("total_duration_seconds")
        if isinstance(duration, (int, float)):
            total_duration += duration
    return {
        "engines": len(metrics),
        "execution_count": total_executions,
        "failure_count": total_failures,
        "total_duration_seconds": total_duration,
        "engines_detail": [dict(metric) for metric in metrics],
    }
