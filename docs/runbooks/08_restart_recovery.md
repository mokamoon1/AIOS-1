# Runbook 08 - Restart / Recovery

Clean and crash recovery of the Core Engine. Startup order
(`src/aios/core/engine.py`): config -> logging -> database -> event bus ->
agents -> engines -> trading controls -> broker -> providers -> ingestion ->
metrics server -> alert manager -> order timeout monitor.

## Trigger

- Scheduled maintenance / deployment.
- Crash, hang, or degraded state requiring a clean boot.

## Procedure (clean restart)

1. Stop the engine:

   ```python
   await core.shutdown()   # runs _teardown_components
   ```

   Teardown order: metrics server stop (frees the metrics port) -> order
   timeout scan cancel -> alert manager stop -> broker disconnect event ->
   providers disconnect -> engines/agents unregister -> DB engine dispose.

2. Confirm no process still holds the metrics port
   (`monitoring.metrics_port`, default 9090):

   ```bash
   netstat -ano | findstr :9090
   ```

3. Boot the engine again (`CoreEngine(environment=..., clock=...)`). The clock
   is injected as the market-session `now_fn`; do not change the clock between
   runs or the market guard will disagree with the rest of the system.
4. Verify health: `[02] Health / status reporting` of the operational
   validation, then confirm a fresh `BROKER_CONNECTED` event.

## Procedure (crash recovery)

1. Check `logs/operational_validation.txt` / `logs/aios.log` for the failure
   point (e.g. a `SystemExit: 3` from a uvicorn metrics startup failure, which
   is now guarded and logged instead of taking the process down).
2. Remove any stale lock/pid state, ensure port 9090 is free, and boot.
3. Run the restart-recovery check:

   ```bash
   python tools/operational_validation.py   # test 13 exercises shutdown + reboot
   ```

## Verification

- Test 13 (`[13] Restart / Recovery`) passes: persisted orders/fills/positions
  survive a restart and a second core boots on the same ports.
