# Phase 9.6 Operations Runbooks

Runbooks for the Phase 9.6 execution hardening controls (AIOS-706). Each runbook
covers one operational scenario: how to detect it, the exact procedures, and how
to verify the system recovered.

| # | Runbook | Scope |
|---|---------|-------|
| 01 | [Manual Kill Switch](01_manual_kill_switch.md) | Emergency stop / clear from ops console |
| 02 | [Automatic Stop](02_automatic_stop.md) | Error-rate alert escalation to a full stop |
| 03 | [Alert Response](03_alert_response.md) | Triage of alerting rules, windows, cooldowns |
| 04 | [Order Timeout Scan](04_order_timeout_scan.md) | Stale pending order cancellation |
| 05 | [Retry / Backoff](05_retry_backoff.md) | Transient broker failure handling |
| 06 | [Market Session / Holiday](06_market_session_holiday.md) | Session windows and holiday maintenance |
| 07 | [Broker Disconnect](07_broker_disconnect.md) | Connectivity loss and reconnection |
| 08 | [Restart / Recovery](08_restart_recovery.md) | Clean and crash restart of the Core Engine |
| 09 | [Benchmark / Trend](09_benchmark_trend.md) | Latency benchmarks and trend analysis |

## Core concepts

- All execution-side controls live on the broker order path and are enforced
  through a `GuardChain` (`aios.brokers.guards.GuardChain`). A failing guard
  raises `TradeBlockedError` and no order reaches the broker.
- Every control writes an event into the shared `EventLog`
  (`aios.monitoring.event_log.EventLog`). Events are the single source of truth
  for the alerting rules and for audit/recovery.
- All time-dependent controls are clock-injectable (`now_fn`, `clock`) so
  runbooks, tests, and validation can be run deterministically.

## Configuration

Controls are configured in the `[trading]` section of the active environment
TOML (e.g. `config/config.paper.toml`), environment prefix `AIOS_TRADING_`.

```toml
[trading]
emergency_stop_enabled = true
order_timeout_enabled = true
pending_order_timeout_seconds = 300
order_timeout_scan_interval_seconds = 30
retry_enabled = true
retry_max_attempts = 3
retry_base_delay_ms = 200
retry_max_delay_ms = 2000
retry_backoff_factor = 2.0
market_session_enabled = true
market_timezone = "America/New_York"
market_open = "09:30"
market_close = "16:00"
market_holidays = []
```
