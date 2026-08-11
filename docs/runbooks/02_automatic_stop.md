# Runbook 02 - Automatic Stop

An alerting rule that has escalated to a critical severity can justify halting
execution. The system provides the building blocks: the kill switch (Runbook 01)
is the enforcement mechanism, and the alerting rules (Runbook 03) are the
detection mechanism.

## Trigger

- Error rate on an operation component exceeds the configured alert threshold
  for the alert window.
- A Shariah violation or gate failure is observed on the order path.
- Broker disconnect persists longer than the configured window.

## How it works

- `AlertManager` consumes `EVENT_ERROR` / `EVENT_OPERATION` events from the
  `EventLog` and fires `AlertRule`s. Each fired rule increments the rule's
  `fire_count` and is subject to `cooldown_seconds` (a rule cannot re-fire
  before the cooldown elapses).
- Firing is best-effort; it must never block the order path. Any operator
  decision to stop the system is applied through the kill switch.

## Procedure

1. Confirm the alert is firing from the monitoring dashboard or
   `tests/reports/` artifacts.
2. Inspect the `EventLog` for the relevant events:

   ```python
   log.count_in_window("ERROR", seconds=300)
   log.entries("SHARIAH_VIOLATION")
   log.entries("GATE_FAILURE")
   ```

3. Decide: if the condition is a hard compliance failure, trigger the kill
   switch per Runbook 01.
4. Record the decision and the follow-up in the incident tracker; reference the
   event entries.

## Verification

The alert rule's `last_fired_at` advances, `fire_count` increments, and the
event window is recorded. Covered by:

```bash
python -m pytest tests/unit/monitoring/test_alerting.py -q
```

## Notes

- The kill switch is an operator action, not an automatic side effect of an
  alert. The runbook keeps the two concerns separate so that no code path can
  self-disable the order path accidentally.
