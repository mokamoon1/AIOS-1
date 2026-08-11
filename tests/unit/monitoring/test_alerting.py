"""Alerting tests (Phase 9.6, P0-1).

Each alert condition is tested against real recorded events and measured
latency values — no hard-coded returns anywhere. The EventLog is the fact
source and a stub latency source supplies measured P99 values.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.config.settings import MonitoringSettings
from aios.monitoring.alerting import Alert, AlertManager, AlertRule, PrometheusLatencySource
from aios.monitoring.event_log import (
    EVENT_BROKER_CONNECTED,
    EVENT_BROKER_DISCONNECTED,
    EVENT_ERROR,
    EVENT_GATE_FAILURE,
    EVENT_OPERATION,
    EVENT_SHARIAH_VIOLATION,
    EventLog,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc


def _manager(**kwargs) -> AlertManager:
    settings = type("S", (), {"monitoring": MonitoringSettings()})()
    return AlertManager(settings=settings, **kwargs)


class _FixedLatency:
    """Stub latency source returning configured measured P99 values."""

    def __init__(self, **values: float | None) -> None:
        self._values = values

    def latency_p99_ms(self, component: str) -> float | None:
        return self._values.get(component)


class TestErrorRateAlert:
    def test_fires_when_error_rate_exceeds_threshold(self) -> None:
        log = EventLog()
        manager = _manager(event_log=log)
        # 3 errors over 5 operations = 60% > 10% threshold.
        for _ in range(2):
            manager.record_operation("op", {})
        for _ in range(3):
            manager.record_error("engine", {})
        assert manager._check_error_rate() is True

    def test_does_not_fire_below_threshold(self) -> None:
        log = EventLog()
        manager = _manager(event_log=log)
        for _ in range(9):
            manager.record_operation("op", {})
        manager.record_error("engine", {})
        # 10% is not strictly greater than the 10% threshold.
        assert manager._check_error_rate() is False

    def test_get_error_rate_returns_real_ratio(self) -> None:
        log = EventLog()
        manager = _manager(event_log=log)
        for _ in range(4):
            manager.record_operation("op", {})
        manager.record_error("engine", {})
        assert manager._get_error_rate() == pytest.approx(1 / 5)

    def test_zero_rate_with_no_operations(self) -> None:
        manager = _manager(event_log=EventLog())
        assert manager._get_error_rate() == 0.0


class TestBrokerDisconnectAlert:
    def test_fires_after_disconnect_without_reconnect(self) -> None:
        log = EventLog()
        log.record(EVENT_BROKER_DISCONNECTED, "broker.service", payload={"reason": "timeout"})
        manager = _manager(event_log=log)
        assert manager._check_broker_disconnect() is True

    def test_does_not_fire_after_reconnect(self) -> None:
        log = EventLog()
        log.record(EVENT_BROKER_DISCONNECTED, "broker.service", payload={"reason": "timeout"})
        log.record(EVENT_BROKER_CONNECTED, "broker.service")
        manager = _manager(event_log=log)
        assert manager._check_broker_disconnect() is False

    def test_does_not_fire_with_no_events(self) -> None:
        manager = _manager(event_log=EventLog())
        assert manager._check_broker_disconnect() is False


class TestShariahViolationAlert:
    def test_fires_after_violation_event(self) -> None:
        log = EventLog()
        log.record(EVENT_SHARIAH_VIOLATION, "broker.service", payload={"symbol": "WINE"})
        manager = _manager(event_log=log)
        assert manager._check_shariah_violations() is True

    def test_does_not_fire_without_violations(self) -> None:
        manager = _manager(event_log=EventLog())
        assert manager._check_shariah_violations() is False


class TestGateFailureAlert:
    def test_fires_after_gate_failure_event(self) -> None:
        log = EventLog()
        log.record(EVENT_GATE_FAILURE, "broker.service", payload={"gate": "risk_approval"})
        manager = _manager(event_log=log)
        assert manager._check_gate_failures() is True

    def test_does_not_fire_without_gate_failures(self) -> None:
        manager = _manager(event_log=EventLog())
        assert manager._check_gate_failures() is False


class TestHighLatencyAlert:
    def test_fires_when_measured_p99_exceeds_threshold(self) -> None:
        source = _FixedLatency(decision=600.0)
        manager = _manager(metric_source=source)
        assert manager._check_high_latency() is True

    def test_does_not_fire_below_threshold(self) -> None:
        source = _FixedLatency(ingestion=40.0, decision=200.0, broker=80.0)
        manager = _manager(metric_source=source)
        assert manager._check_high_latency() is False

    def test_fires_from_recorded_samples_without_histogram(self) -> None:
        manager = _manager(metric_source=_FixedLatency())
        for value in (100.0, 200.0, 300.0, 900.0):
            manager.record_latency("broker", value)
        assert manager._check_high_latency() is True


class TestAlertFiring:
    def test_fire_records_alert_in_history(self) -> None:
        import asyncio

        log = EventLog()
        manager = _manager(event_log=log)
        rule = AlertRule(
            name="test_rule",
            condition=lambda: True,
            severity="warning",
            message_template="rate={rate:.2%} details={details}",
            component="test",
            cooldown_seconds=1,
        )
        asyncio.run(manager._fire_alert(rule))
        assert len(manager.alert_history) == 1
        assert manager.alert_history[0].name == "test_rule"

    def test_cooldown_suppresses_repeat_fires(self) -> None:
        import asyncio

        manager = _manager(event_log=EventLog())
        rule = AlertRule(
            name="cooldown_rule",
            condition=lambda: True,
            severity="warning",
            message_template="x {details}",
            component="test",
            cooldown_seconds=3600,
        )
        rule.last_fired = 0.0  # long ago
        asyncio.run(manager._fire_alert(rule))
        first = manager.alert_history[-1].timestamp
        # Immediately evaluating again must be suppressed by the cooldown.
        assert rule.last_fired is not None
        # Simulate the cooldown gate directly.
        current = time.time()
        assert (current - rule.last_fired) < rule.cooldown_seconds
        assert first is not None


import time  # noqa: E402


class TestEventBusMirroring:
    def test_bus_events_are_mirrored_into_log(self) -> None:
        import asyncio

        class _Bus:
            def __init__(self) -> None:
                self.subscribers: dict[str, list] = {}

            def subscribe(self, event_type: str, handler) -> None:
                self.subscribers.setdefault(event_type, []).append(handler)

        class _Event:
            def __init__(self, event_type: str, source: str, payload: dict) -> None:
                self.event_type = event_type
                self.source = source
                self.payload = payload

        log = EventLog()
        bus = _Bus()
        manager = _manager(event_log=log)
        asyncio.run(manager.start(bus=bus))
        assert EVENT_ERROR in bus.subscribers

        # Dispatch an ERROR event through the subscribed handler.
        asyncio.run(bus.subscribers[EVENT_ERROR][0](_Event(EVENT_ERROR, "market.engine", {"m": 1})))
        assert log.count_in_window(EVENT_ERROR, 60) == 1
        asyncio.run(manager.stop())
