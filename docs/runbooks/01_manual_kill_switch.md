# Runbook 01 - Manual Kill Switch

Emergency stop that blocks all execution on the paper order path until explicitly
cleared. Enforced by `EmergencyStopGuard` inside the `GuardChain` on
`BrokerService` (order submission, fill, cancel, reject).

## Trigger

- A human operator (or the ops console) decides all order activity must halt.
- `emergency_stop_enabled = true` in `[trading]`.

## How it works

`EmergencyStopManager.trigger_stop()` records an `EMERGENCY_STOP` event in the
`EventLog` and flips the internal stop flag. Every subsequent order operation
raises `TradeBlockedError(code="emergency_stop", reason=...)`. The flag and the
event are cleared by `clear_stop()`.

## Procedure

1. Trigger the stop:

   ```python
   from aios.monitoring.emergency_stop import EmergencyStopManager
   mgr = EmergencyStopManager(event_log=event_log)
   mgr.trigger_stop(triggered_by="ops-console", reason="manual review")
   ```

2. Confirm the order path is blocked:

   ```python
   guard = EmergencyStopGuard(mgr)
   guard.assert_allows(order)  # raises TradeBlockedError until cleared
   ```

3. Resolve the underlying issue, then clear the stop (acknowledge first if
   required by policy):

   ```python
   mgr.acknowledge_stop(acknowledged_by="on-call")
   mgr.clear_stop(cleared_by="ops-console")
   ```

4. Verify recovery: an `EMERGENCY_CLEAR` event is recorded and the next order
   operation passes the guard.

## Verification

```bash
python -m pytest tests/unit/brokers/test_kill_switch.py -q
```

## Notes

- `clear_stop()` only lifts the kill switch; the remaining guards (market
  session, risk gates, Shariah gate) still apply.
- The stop is process-local. After a restart the manager starts in the clear
  state; see Runbook 08.
