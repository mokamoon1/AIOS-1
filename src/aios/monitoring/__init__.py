"""Monitoring and observability package (AIOS-107 section 10, AIOS-807 section 7).

The package reports operational health snapshots: system health, data
availability, agent status, errors, and performance. No alert thresholds are
defined here because the approved documents specify none (AIOS-705 section
13); the snapshot is an integration point for monitoring tooling.
"""

from __future__ import annotations

from aios.monitoring.health import HealthMonitor, HealthSnapshot
from aios.monitoring.metrics import (
    metrics_endpoint,
    metrics_middleware,
    record_http_request,
    record_http_latency,
    record_ingestion,
    record_decision,
    record_broker_order,
    record_broker_fill,
    record_risk_evaluation,
    record_shariah_check,
    record_error,
    update_system_metrics,
)
from aios.monitoring.alerting import AlertManager, create_alert_manager, Alert, AlertRule
from aios.monitoring.emergency_stop import EmergencyStopManager, create_emergency_stop_manager, StopReason, StopEvent
from aios.monitoring.event_log import EventEntry, EventLog
from aios.monitoring.metrics import (
    decision_latency_p99_ms,
    ingestion_latency_p99_ms,
    broker_fill_latency_p99_ms,
)

__all__ = [
    "HealthMonitor",
    "HealthSnapshot",
    "metrics_endpoint",
    "metrics_middleware",
    "record_http_request",
    "record_http_latency",
    "record_ingestion",
    "record_decision",
    "record_broker_order",
    "record_broker_fill",
    "record_risk_evaluation",
    "record_shariah_check",
    "record_error",
    "update_system_metrics",
    "AlertManager",
    "create_alert_manager",
    "Alert",
    "AlertRule",
    "EmergencyStopManager",
    "create_emergency_stop_manager",
    "StopReason",
    "StopEvent",
    "EventLog",
    "EventEntry",
    "ingestion_latency_p99_ms",
    "decision_latency_p99_ms",
    "broker_fill_latency_p99_ms",
]
