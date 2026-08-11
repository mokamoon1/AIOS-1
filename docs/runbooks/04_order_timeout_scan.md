# Runbook 04 - Order Timeout Scan

Detects and cancels pending paper orders that have been stuck longer than
`pending_order_timeout_seconds` (default 300s), recording an `ORDER_TIMEOUT`
audit event for each cancellation.

## Trigger

- A `PENDING` order has `updated_at <= now - pending_order_timeout_seconds`.
- `order_timeout_enabled = true` in `[trading]`.

## How it works

`PendingOrderTimeoutMonitor.cancel_expired(orders, now=...)`:

- Selects only `PENDING` orders (`FILLED`, `CANCELLED`, `REJECTED` are never
  touched).
- For each expired order, calls `broker.cancel_order(order_id)` and records
  `EVENT_ORDER_TIMEOUT` with `order_id`, `status_after`, and `timeout_seconds`.
- A cancellation failure is logged and the order is skipped (the next scan
  retries it).

The Core Engine starts the monitor as a periodic scan task
(`_start_order_timeout_monitor`) at `order_timeout_scan_interval_seconds`
(default 30s) and cancels it during teardown.

## Procedure

1. Check the event log for recent timeouts:

   ```python
   log.entries("ORDER_TIMEOUT")
   ```

2. If an order repeatedly times out, investigate the broker route (Runbook 07)
   or raise the configured timeout.
3. Manual scan:

   ```python
   from aios.brokers.timeout import PendingOrderTimeoutMonitor
   monitor = PendingOrderTimeoutMonitor(broker, timeout_seconds=300)
   expired = monitor.expired_pending(broker.list_orders(), now=now)
   cancelled = monitor.cancel_expired(broker.list_orders(), now=now)
   ```

## Verification

```bash
python -m pytest tests/unit/brokers/test_timeout.py -q
```
