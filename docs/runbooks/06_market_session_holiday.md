# Runbook 06 - Market Session / Holiday

`MarketSessionGuard` blocks order activity outside configured market hours and
on configured holidays. It is enforced inside the `GuardChain` on the broker
order path and records `EVENT_MARKET_CLOSED`.

## Trigger

- Order submission outside `market_open`..`market_close` in `market_timezone`.
- Order submission on a date in `market_holidays`.

## How it works

`MarketSessionGuard.from_settings(trading, now_fn=...)` reads:

```toml
[trading]
market_session_enabled = true
market_timezone = "America/New_York"
market_open = "09:30"
market_close = "16:00"
market_holidays = []   # e.g. ["2026-08-06"]
```

- `is_open(at)` returns whether the given (or current) timestamp is within a
  trading session on a non-holiday weekday.
- `closed_reason(at)` returns a human-readable reason (e.g. after close,
  weekend, holiday) or `None` when open.
- The Core Engine injects its `clock` as `now_fn` so the guard and the rest of
  the engine agree on the current time.

## Procedure

1. Before a scheduled market holiday, add the date to `market_holidays` in the
   active `[trading]` config and restart the Core Engine (Runbook 08).
2. Confirm the guard state:

   ```python
   from aios.brokers.market_session import MarketSessionGuard
   guard = MarketSessionGuard.from_settings(trading_settings, now_fn=now)
   guard.is_open(now)          # False outside hours
   guard.closed_reason(now)    # e.g. "market closed: 17:00 at/after close 16:00:00"
   ```

3. Orders attempted while closed raise
   `TradeBlockedError(code="market_closed", reason=...)`.

## Verification

```bash
python -m pytest tests/unit/brokers/test_market_session.py -q
```
