"""Health monitoring tests (AIOS-107 section 10, AIOS-807 section 7).

Verifies that the health snapshot is derived strictly from reported state and
never fabricates availability, and that engine performance metrics are
aggregated for trend reporting (AIOS-705 section 12, AIOS-605 section 16).
"""

from __future__ import annotations

import pytest

from aios.monitoring.health import HealthMonitor, HealthSnapshot

pytestmark = pytest.mark.unit


def _ready_status() -> dict:
    return {
        "state": "ready",
        "environment": "testing",
        "components": {
            "configuration": True,
            "logging": True,
            "database": True,
            "event_bus": True,
            "broker": False,
            "agents": {"loaded": 7, "ready": 7},
            "engines": {"loaded": 6, "ready": 6},
            "providers": {"connected": 0},
        },
    }


class TestHealthSnapshot:
    def test_defaults_do_not_fabricate_availability(self) -> None:
        snapshot = HealthSnapshot()
        assert snapshot.service_available is False
        assert snapshot.data_available is False
        assert snapshot.broker_connected is False
        assert snapshot.agent_loaded == 0
        assert snapshot.engine_loaded == 0
        assert snapshot.error_counts == {}
        assert snapshot.performance == {}


class TestHealthMonitor:
    def test_snapshot_from_ready_status(self) -> None:
        snapshot = HealthMonitor().snapshot(_ready_status())
        assert snapshot.state == "ready"
        assert snapshot.environment == "testing"
        assert snapshot.service_available is True
        assert snapshot.data_available is True
        assert snapshot.broker_connected is False
        assert snapshot.agent_loaded == 7
        assert snapshot.agent_ready == 7
        assert snapshot.engine_loaded == 6
        assert snapshot.engine_ready == 6
        assert snapshot.providers_connected == 0

    def test_snapshot_reflects_broker_connectivity(self) -> None:
        status = _ready_status()
        status["components"]["broker"] = True
        snapshot = HealthMonitor().snapshot(status)
        assert snapshot.broker_connected is True

    def test_non_ready_state_is_not_available(self) -> None:
        status = _ready_status()
        status["state"] = "failed"
        snapshot = HealthMonitor().snapshot(status)
        assert snapshot.service_available is False

    def test_empty_status_yields_defaults(self) -> None:
        snapshot = HealthMonitor().snapshot({})
        assert snapshot.service_available is False
        assert snapshot.data_available is False
        assert snapshot.environment is None

    def test_error_counts_are_included(self) -> None:
        snapshot = HealthMonitor().snapshot(_ready_status(), error_counts={"ERROR": 2})
        assert snapshot.error_counts == {"ERROR": 2}

    def test_engine_metrics_aggregated(self) -> None:
        metrics = [
            {
                "engine_type": "technical",
                "execution_count": 3,
                "failure_count": 1,
                "total_duration_seconds": 1.5,
            },
            {
                "engine_type": "decision",
                "execution_count": 2,
                "failure_count": 0,
                "total_duration_seconds": 0.5,
            },
        ]
        snapshot = HealthMonitor().snapshot(_ready_status(), engine_metrics=metrics)
        assert snapshot.performance["engines"] == 2
        assert snapshot.performance["execution_count"] == 5
        assert snapshot.performance["failure_count"] == 1
        assert snapshot.performance["total_duration_seconds"] == pytest.approx(2.0)
        assert len(snapshot.performance["engines_detail"]) == 2
