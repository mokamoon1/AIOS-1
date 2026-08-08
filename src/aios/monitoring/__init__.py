"""Monitoring and observability package (AIOS-107 section 10, AIOS-807 section 7).

The package reports operational health snapshots: system health, data
availability, agent status, errors, and performance. No alert thresholds are
defined here because the approved documents specify none (AIOS-705 section
13); the snapshot is an integration point for monitoring tooling.
"""

from __future__ import annotations

from aios.monitoring.health import HealthMonitor, HealthSnapshot

__all__ = ["HealthMonitor", "HealthSnapshot"]
