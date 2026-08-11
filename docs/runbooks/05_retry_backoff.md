# Runbook 05 - Retry / Backoff

`BrokerService` retries broker calls that fail with a transient error, using a
bounded exponential backoff. Retry is configured in `[trading]`
(`retry_enabled`, `retry_max_attempts`, `retry_base_delay_ms`,
`retry_max_delay_ms`, `retry_backoff_factor`).

## Trigger

- A broker call raises `BrokerTransientError`, `ConnectionError`,
  `TimeoutError`, or `OSError` while the retry policy is enabled.

## How it works

`RetryPolicy.run(operation)`:

- Retries only transient errors (`is_transient`); validation, security, Shariah,
  and gate failures are never retried.
- Backoff is exponential and bounded:
  `base_delay * backoff_factor^(attempt-1)`, capped at `retry_max_delay_ms`.
- If the same order was already created (`OrderAlreadyExistsError`), the retry is
  treated as an idempotent success rather than an error.
- On exhaustion, `BrokerRetryExhaustedError` is raised carrying the attempt
  count and the last error.

## Procedure

1. Confirm the failure was transient by inspecting the engine log for the
   exception type.
2. If retries are failing consistently, raise the attempt/delay settings, or
   fix the broker route before resubmitting.
3. Manual invocation with an explicit policy:

   ```python
   from aios.brokers.retry import RetryPolicy
   policy = RetryPolicy.from_settings(trading_settings)
   result = policy.run(operation)  # .attempts, .last_error
   ```

## Verification

```bash
python -m pytest tests/unit/brokers/test_retry.py -q
```

## Notes

- `retry_enabled = false` disables retry entirely: the operation is attempted
  exactly once and transient errors propagate to the caller.
