# Runbook 03 - Alert Response

The alerting subsystem (`aios.monitoring.alerting.AlertManager`) turns events in
the shared `EventLog` into alerts. The configured rules:

- Error-rate rule: `ERROR` events over `OPERATION` events for a component exceed
  the configured fraction (default `0.10`) in `alert_window_seconds` (300s).
- Broker-disconnect rule: a `BROKER_DISCONNECTED` event without a following
  `BROKER_CONNECTED` event within the window.
- Shariah-violation rule: any `SHARIAH_VIOLATION` event in the window.
- Gate-failure rule: any `GATE_FAILURE` event in the window.
- Latency rule: measured P99 latency for a component exceeds the configured
  threshold (latency samples flow through `record_latency(component, ms)`).

## Trigger

Any rule condition becoming true. Each rule has `cooldown_seconds` (default 300)
so a sustained condition fires once per window, not per sample.

## Procedure

1. Identify which rule fired and its `last_fired_at` / `fire_count`.
2. Pull the underlying events:

   ```python
   log.entries()                     # all events, newest last
   log.count_since("BROKER_DISCONNECTED", since=since)
   log.has_recent("GATE_FAILURE", seconds=300)
   ```

3. For latency alerts, query the metrics endpoint
   `GET /metrics` (Prometheus) or call
   `ingestion_latency_p99_ms()`, `decision_latency_p99_ms()`,
   `broker_fill_latency_p99_ms()`.
4. Resolve the root cause (broker reconnect, data quality, config), then verify
   the next event window contains no re-fire.

## Wiring

`AlertManager.start(bus=event_bus)` subscribes the manager to the event bus so
runtime events (errors, disconnects) are mirrored into the `EventLog`. It must be
stopped during engine teardown: `await alert_manager.stop()`.

## Verification

```bash
python -m pytest tests/unit/monitoring/test_alerting.py tests/unit/monitoring/test_event_log.py -q
```
