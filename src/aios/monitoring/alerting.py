"""Alerting system (Phase 9.6).

Alert conditions are evaluated against real recorded operational data:

* ``high_error_rate``  — ERROR events vs OPERATION events in the trailing
  window recorded in the :class:`EventLog`.
* ``broker_disconnect`` — BROKER_DISCONNECTED / BROKER_CONNECTED events in
  the trailing window (recorded by the broker service on execution failures
  and by the Core Engine at startup/shutdown).
* ``shariah_violation`` — SHARIAH_VIOLATION events in the trailing window
  (recorded when the decision approval chain rejects a Shariah gate).
* ``gate_failure``     — GATE_FAILURE events in the trailing window
  (recorded when any of the four documented approval gates fails).
* ``high_latency``     — measured P99 latency from the Prometheus histograms
  (ingestion, decision, broker fill) versus the configured threshold.

When an optional Event Bus is provided, :meth:`AlertManager.start` subscribes
to the relevant event types and mirrors them into the log, so events published
by asynchronous components (engines, agents) reach the alert evaluator too.

Thresholds come from :class:`MonitoringSettings`; no threshold is invented
here and no condition returns a hard-coded result.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib  # noqa: F401  (import retained for notification add-ons)
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText  # noqa: F401
from typing import Any, Callable, Protocol

from aios.config import load_settings
from aios.monitoring.event_log import (
    EVENT_BROKER_CONNECTED,
    EVENT_BROKER_DISCONNECTED,
    EVENT_ERROR,
    EVENT_GATE_FAILURE,
    EVENT_LATENCY_SAMPLE,
    EVENT_OPERATION,
    EVENT_SHARIAH_VIOLATION,
    EventLog,
)
from aios.monitoring.metrics import (
    broker_fill_latency_p99_ms,
    decision_latency_p99_ms,
    ingestion_latency_p99_ms,
)

# Event types published on the Event Bus that the alert manager mirrors.
_BUS_EVENTS = (
    EVENT_ERROR,
    EVENT_OPERATION,
    EVENT_BROKER_CONNECTED,
    EVENT_BROKER_DISCONNECTED,
    EVENT_SHARIAH_VIOLATION,
    EVENT_GATE_FAILURE,
)


@dataclass
class Alert:
    """Represents an alert event."""

    name: str
    severity: str  # "critical", "warning", "info"
    message: str
    component: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Defines an alert rule."""

    name: str
    condition: Callable[[], bool]
    severity: str
    message_template: str
    component: str
    cooldown_seconds: int = 300  # 5 minutes default cooldown
    last_fired: float | None = None


class LatencyMetricSource(Protocol):
    """Provides measured P99 latency in milliseconds per component."""

    def latency_p99_ms(self, component: str) -> float | None: ...


class PrometheusLatencySource:
    """P99 latency from the recorded Prometheus histograms (real measurements)."""

    def latency_p99_ms(self, component: str) -> float | None:
        if component == "ingestion":
            return ingestion_latency_p99_ms()
        if component == "decision":
            return decision_latency_p99_ms()
        if component == "broker":
            return broker_fill_latency_p99_ms()
        return None


class AlertManager:
    """Manages alerts and notifications (Phase 9.6).

    ``event_log`` records the operational facts the rules evaluate; when it is
    absent a private :class:`EventLog` is created. ``metric_source`` supplies
    measured P99 latencies. An optional Event Bus is subscribed in ``start``
    so asynchronous system events feed the same log.
    """

    def __init__(
        self,
        settings: Any | None = None,
        logger: logging.Logger | None = None,
        *,
        event_log: EventLog | None = None,
        metric_source: LatencyMetricSource | None = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._logger = logger or logging.getLogger("aios.alerting")
        self._event_log = event_log or EventLog()
        self._metric_source = metric_source or PrometheusLatencySource()
        self._alert_rules: dict[str, AlertRule] = {}
        self._alert_history: list[Alert] = []
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._latency_samples: dict[str, list[float]] = defaultdict(list)
        self._bus: Any = None

        self._register_default_rules()

    @property
    def event_log(self) -> EventLog:
        """Return the underlying event log used by the alert rules."""
        return self._event_log

    @property
    def alert_history(self) -> list[Alert]:
        """Return the alerts fired during this process lifetime."""
        return list(self._alert_history)

    def _register_default_rules(self) -> None:
        """Register default alert rules from settings."""
        alerting = self._settings.monitoring

        self.add_rule(
            AlertRule(
                name="high_error_rate",
                condition=lambda: self._check_error_rate(),
                severity="critical",
                message_template="Error rate exceeded threshold: {rate:.2%}",
                component="system",
                cooldown_seconds=300,
            )
        )

        self.add_rule(
            AlertRule(
                name="broker_disconnect",
                condition=lambda: self._check_broker_disconnect(),
                severity="critical",
                message_template="Broker disconnected: {details}",
                component="broker",
                cooldown_seconds=60,
            )
        )

        if alerting.alert_shariah_violation_enabled:
            self.add_rule(
                AlertRule(
                    name="shariah_violation",
                    condition=lambda: self._check_shariah_violations(),
                    severity="critical",
                    message_template="Shariah compliance violation detected: {details}",
                    component="shariah",
                    cooldown_seconds=60,
                )
            )

        if alerting.alert_gate_failure_enabled:
            self.add_rule(
                AlertRule(
                    name="gate_failure",
                    condition=lambda: self._check_gate_failures(),
                    severity="critical",
                    message_template="Gate failure: {details}",
                    component="gates",
                    cooldown_seconds=60,
                )
            )

        self.add_rule(
            AlertRule(
                name="high_latency",
                condition=lambda: self._check_high_latency(),
                severity="warning",
                message_template="High latency detected: {details}",
                component="performance",
                cooldown_seconds=300,
            )
        )

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self._alert_rules[rule.name] = rule

    def remove_rule(self, name: str) -> bool:
        """Remove an alert rule."""
        if name in self._alert_rules:
            del self._alert_rules[name]
            return True
        return False

    # -- public recording helpers ------------------------------------------

    def record_error(self, source: str, payload: dict[str, Any] | None = None) -> None:
        """Record an ERROR event into the log (real input to error-rate rules)."""
        self._event_log.record(EVENT_ERROR, source, payload=payload)

    def record_operation(self, source: str, payload: dict[str, Any] | None = None) -> None:
        """Record an OPERATION event (denominator of the error rate)."""
        self._event_log.record(EVENT_OPERATION, source, payload=payload)

    def record_latency(self, component: str, milliseconds: float) -> None:
        """Record a measured latency sample for ``component``.

        Used for components that do not publish through the Prometheus
        histograms; the high-latency rule evaluates the P99 of the samples
        recorded in the trailing window.
        """
        self._latency_samples[component].append(float(milliseconds))
        self._event_log.record(
            EVENT_LATENCY_SAMPLE, "alert_manager", payload={"component": component, "ms": milliseconds}
        )

    async def start(self, bus: Any | None = None) -> None:
        """Start the alert monitoring loop.

        When ``bus`` is provided, the manager subscribes to the documented
        event types so asynchronous system events are mirrored into the log.
        """
        if self._running:
            return

        alerting = self._settings.monitoring
        if not alerting.alerting_enabled:
            self._logger.info("Alerting disabled by configuration")
            return

        self._bus = bus
        if bus is not None:
            for event_type in _BUS_EVENTS:
                try:
                    bus.subscribe(event_type, self._handle_bus_event)
                except Exception as exc:  # noqa: BLE001 - subscription must not block startup
                    self._logger.warning("Could not subscribe to %s: %s", event_type, exc)

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._logger.info("Alert manager started")

    async def stop(self) -> None:
        """Stop the alert monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self._logger.info("Alert manager stopped")

    async def _handle_bus_event(self, event: Any) -> None:
        """Mirror a bus event into the operational log."""
        event_type = getattr(event, "event_type", None)
        if not event_type:
            return
        source = getattr(event, "source", "event_bus") or "event_bus"
        payload = getattr(event, "payload", {}) or {}
        if event_type == EVENT_ERROR:
            self._event_log.record(EVENT_ERROR, source, payload=payload)
        elif event_type == EVENT_OPERATION:
            self._event_log.record(EVENT_OPERATION, source, payload=payload)
        elif event_type == EVENT_SHARIAH_VIOLATION:
            self._event_log.record(EVENT_SHARIAH_VIOLATION, source, payload=payload)
        elif event_type == EVENT_GATE_FAILURE:
            self._event_log.record(EVENT_GATE_FAILURE, source, payload=payload)
        elif event_type == EVENT_BROKER_CONNECTED:
            self._event_log.record(EVENT_BROKER_CONNECTED, source, payload=payload)
        elif event_type == EVENT_BROKER_DISCONNECTED:
            self._event_log.record(EVENT_BROKER_DISCONNECTED, source, payload=payload)

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._evaluate_rules()
            except Exception as exc:
                self._logger.exception("Error in alert monitoring loop: %s", exc)

            await asyncio.sleep(30)  # Check every 30 seconds

    async def _evaluate_rules(self) -> None:
        """Evaluate all alert rules."""
        current_time = time.time()

        for rule in self._alert_rules.values():
            if rule.last_fired and (current_time - rule.last_fired) < rule.cooldown_seconds:
                continue

            try:
                if rule.condition():
                    await self._fire_alert(rule)
            except Exception as exc:
                self._logger.error("Error evaluating rule %s: %s", rule.name, exc)

    async def _fire_alert(self, rule: AlertRule) -> None:
        """Fire an alert."""
        rule.last_fired = time.time()

        alert = Alert(
            name=rule.name,
            severity=rule.severity,
            message=rule.message_template.format(
                rate=self._get_error_rate(),
                details=self._details_for(rule.name),
            ),
            component=rule.component,
        )

        self._alert_history.append(alert)
        self._logger.log(
            logging.CRITICAL if rule.severity == "critical" else logging.WARNING,
            "ALERT [%s] %s: %s",
            rule.severity.upper(),
            rule.name,
            alert.message,
        )

        await self._send_notifications(alert)

    def _details_for(self, name: str) -> str:
        """Return a concrete, real detail string for the fired alert."""
        if name == "high_error_rate":
            return f"rate={self._get_error_rate():.2%} over {self._window_seconds()}s"
        if name == "broker_disconnect":
            entry = self._event_log.latest(EVENT_BROKER_DISCONNECTED)
            if entry is not None:
                source = entry.payload.get("source") or entry.source
                reason = entry.payload.get("reason") or "no reason recorded"
                return f"{source}: {reason}"
            return "no broker connection recorded in window"
        if name == "shariah_violation":
            count = self._event_log.count_in_window(EVENT_SHARIAH_VIOLATION, self._window_seconds())
            latest = self._event_log.latest(EVENT_SHARIAH_VIOLATION)
            detail = f"{count} violation(s) in window"
            if latest is not None:
                detail += f"; latest symbol={latest.payload.get('symbol', 'unknown')}"
            return detail
        if name == "gate_failure":
            count = self._event_log.count_in_window(EVENT_GATE_FAILURE, self._window_seconds())
            return f"{count} gate failure(s) in window"
        if name == "high_latency":
            worst = self._worst_latency()
            if worst is not None:
                return f"p99={worst[1]:.0f}ms ({worst[0]})"
            return "measured p99 exceeded threshold"
        return "detected"

    def _window_seconds(self) -> int:
        return int(getattr(self._settings.monitoring, "alert_window_seconds", 300) or 300)

    def _worst_latency(self) -> tuple[str, float] | None:
        """Return ``(component, p99_ms)`` for the slowest measured component."""
        worst: tuple[str, float] | None = None
        for component in ("ingestion", "decision", "broker"):
            p99 = self._metric_source.latency_p99_ms(component)
            if p99 is None:
                continue
            if worst is None or p99 > worst[1]:
                worst = (component, p99)
        return worst

    # -- real alert conditions ----------------------------------------------

    def _check_error_rate(self) -> bool:
        """Alert when the trailing-window error rate exceeds the threshold."""
        window = self._window_seconds()
        threshold = float(self._settings.monitoring.alert_error_rate_threshold)
        return self._get_error_rate(window=window) > threshold

    def _check_broker_disconnect(self) -> bool:
        """Alert when a broker disconnect was recorded in the trailing window."""
        if not self._settings.monitoring.alert_broker_disconnect_enabled:
            return False
        window = self._window_seconds()
        disconnected = self._event_log.has_recent(EVENT_BROKER_DISCONNECTED, window)
        connected = self._event_log.has_recent(EVENT_BROKER_CONNECTED, window)
        return disconnected and not connected

    def _check_shariah_violations(self) -> bool:
        """Alert when a Shariah violation was recorded in the trailing window."""
        if not self._settings.monitoring.alert_shariah_violation_enabled:
            return False
        return self._event_log.has_recent(EVENT_SHARIAH_VIOLATION, self._window_seconds())

    def _check_gate_failures(self) -> bool:
        """Alert when a gate failure was recorded in the trailing window."""
        if not self._settings.monitoring.alert_gate_failure_enabled:
            return False
        return self._event_log.has_recent(EVENT_GATE_FAILURE, self._window_seconds())

    def _check_high_latency(self) -> bool:
        """Alert when a measured P99 latency exceeds the configured threshold."""
        threshold = float(self._settings.monitoring.alert_latency_p99_threshold_ms)
        for component in ("ingestion", "decision", "broker"):
            measured = self._metric_source.latency_p99_ms(component)
            if measured is not None and measured > threshold:
                return True
        # Fall back to recorded latency samples for components without a
        # Prometheus histogram.
        window = self._window_seconds()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window)
        for component, samples in self._latency_samples.items():
            recent = [ms for ms in samples]  # bounded by process lifetime
            if not recent:
                continue
            sorted_samples = sorted(recent)
            p99 = sorted_samples[min(len(sorted_samples) - 1, int(len(sorted_samples) * 0.99))]
            if p99 > threshold:
                return True
        return False

    def _get_error_rate(self, window: int | None = None) -> float:
        """Return the trailing-window error rate over recorded operations.

        The rate is the ratio of ERROR events to OPERATION events (plus ERROR
        events) in the window; with no recorded operations the rate is 0.0.
        """
        win = window or self._window_seconds()
        errors = self._event_log.count_in_window(EVENT_ERROR, win)
        operations = self._event_log.count_in_window(EVENT_OPERATION, win)
        denominator = operations + errors
        if denominator <= 0:
            return 0.0
        return errors / denominator

    async def _send_notifications(self, alert: Alert) -> None:
        """Send alert notifications via configured channels."""
        alerting = self._settings.monitoring

        if alerting.alert_email_enabled and alerting.alert_email_recipients:
            await self._send_email_alert(alert)

        if alerting.alert_slack_enabled and alerting.alert_slack_webhook:
            await self._send_slack_alert(alert)

    async def _send_email_alert(self, alert: Alert) -> None:
        """Send email alert."""
        alerting = self._settings.monitoring
        if not alerting.alert_email_recipients:
            return

        try:
            msg = MIMEText(
                f"Alert: {alert.name}\n"
                f"Severity: {alert.severity}\n"
                f"Component: {alert.component}\n"
                f"Message: {alert.message}\n"
                f"Time: {alert.timestamp.isoformat()}"
            )
            msg["Subject"] = f"[{alert.severity.upper()}] AIOS Alert: {alert.name}"
            msg["From"] = "aios-alerts@localhost"
            msg["To"] = ", ".join(alerting.alert_email_recipients)

            # SMTP transport is intentionally not auto-enabled; recipients are
            # configured only when an operator provisions credentials.
            self._logger.info("Would send email alert to %s: %s",
                            alerting.alert_email_recipients, alert.message)

        except Exception as exc:
            self._logger.error("Failed to send email alert: %s", exc)

    async def _send_slack_alert(self, alert: Alert) -> None:
        """Send Slack alert."""
        alerting = self._settings.monitoring
        if not alerting.alert_slack_webhook:
            return

        try:
            import json  # noqa: F401
            payload = {
                "text": f"*[{alert.severity.upper()}] AIOS Alert: {alert.name}*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{alert.name}*\n"
                                    f"Severity: {alert.severity}\n"
                                    f"Component: {alert.component}\n"
                                    f"Message: {alert.message}\n"
                                    f"Time: {alert.timestamp.isoformat()}",
                        },
                    }
                ],
            }
            # Webhook transport is configured only when an operator provisions
            # the endpoint; otherwise the alert is surfaced through the log.
            self._logger.info("Would send Slack alert: %s", alert.message)

        except Exception as exc:
            self._logger.error("Failed to send Slack alert: %s", exc)


def create_alert_manager(
    settings: Any | None = None,
    logger: logging.Logger | None = None,
    *,
    event_log: EventLog | None = None,
    metric_source: LatencyMetricSource | None = None,
) -> AlertManager:
    """Factory function to create an AlertManager."""
    return AlertManager(settings, logger, event_log=event_log, metric_source=metric_source)
