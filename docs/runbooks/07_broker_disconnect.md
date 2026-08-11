# Runbook 07 - Broker Disconnect

Detects loss of broker connectivity and drives reconnection. The engine records
`EVENT_BROKER_DISCONNECTED` on shutdown and the alerting subsystem watches for
disconnect events that are not followed by a reconnect.

## Trigger

- `BROKER_DISCONNECTED` event observed, with no `BROKER_CONNECTED` within the
  alert window.
- Paper broker service reporting repeated transient failures (see Runbook 05).

## How it works

- The Core Engine records `EVENT_BROKER_CONNECTED` at startup (broker wired)
  and `EVENT_BROKER_DISCONNECTED` during `_teardown_components` on shutdown.
- The disconnect alert rule fires when a disconnect event is not followed by a
  reconnect event in the window.

## Procedure

1. Confirm the disconnect from the event log:

   ```python
   log.count_since("BROKER_DISCONNECTED", since=ts)
   log.count_since("BROKER_CONNECTED", since=ts)
   ```

2. Verify the broker provider is reachable, then restart the Core Engine
   (Runbook 08); the engine records a fresh `BROKER_CONNECTED` event.
3. Confirm pending orders are handled: orders older than the timeout are
   cancelled by the timeout monitor (Runbook 04); all other pending orders are
   re-evaluated after reconnect.

## Verification

```bash
python -m pytest tests/unit/monitoring/test_alerting.py -q
```

## Notes

- The paper broker is in-process; a disconnect here is a wiring failure rather
  than a remote outage. A real broker adapter follows the same event contract.
