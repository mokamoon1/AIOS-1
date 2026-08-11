"""Bounded exponential-backoff retry for transient broker operations (Phase 9.6, P0-4).

Retries are applied only to *transient* failures (:class:`BrokerTransientError`
and I/O-style exceptions explicitly opted in). Validation, security, approval,
and gate failures are never retried, so a retry can never bypass Shariah or
risk controls. Idempotency is preserved: the same ``order_id`` is reused, and
the policy treats a duplicate-order response during a retry as an idempotent
success (the order already exists).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from aios.brokers.exceptions import (
    BrokerRetryExhaustedError,
    BrokerTransientError,
    OrderAlreadyExistsError,
)

_Clock = Callable[[], float]


def _monotonic_clock() -> float:
    return time.monotonic()


def _delay_seconds(base_ms: int, max_ms: int, backoff_factor: float, attempt: int) -> float:
    """Exponential backoff delay for attempt ``attempt`` (0-based), bounded."""
    raw = base_ms * (backoff_factor ** attempt)
    return min(raw, max_ms) / 1000.0


@dataclass(frozen=True)
class RetryResult:
    """Outcome of a retried operation."""

    value: Any
    attempts: int  # number of attempts actually performed (1..max)
    retried: bool  # True when the first attempt failed and a retry succeeded


class RetryPolicy:
    """Bounded exponential-backoff policy over transient operations."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_delay_ms: int = 200,
        max_delay_ms: int = 2000,
        backoff_factor: float = 2.0,
        clock: _Clock | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if base_delay_ms < 1 or max_delay_ms < base_delay_ms:
            raise ValueError("delay bounds must satisfy 1 <= base_delay_ms <= max_delay_ms")
        if backoff_factor <= 1.0:
            raise ValueError("backoff_factor must be > 1.0")
        self._max_attempts = max_attempts
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        self._backoff_factor = backoff_factor
        self._clock = clock or _monotonic_clock
        self._sleep = sleep_fn or time.sleep
        self._logger = logger or logging.getLogger("aios.brokers.retry")

    @classmethod
    def from_settings(cls, trading: Any, *, logger: logging.Logger | None = None) -> "RetryPolicy":
        """Build a policy from :class:`TradingSettings` (config-driven)."""
        return cls(
            max_attempts=int(getattr(trading, "retry_max_attempts", 3)),
            base_delay_ms=int(getattr(trading, "retry_base_delay_ms", 200)),
            max_delay_ms=int(getattr(trading, "retry_max_delay_ms", 2000)),
            backoff_factor=float(getattr(trading, "retry_backoff_factor", 2.0)),
            logger=logger,
        )

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def delay_before_attempt(self, attempt: int) -> float:
        """Return the sleep in seconds before retry attempt ``attempt``."""
        return _delay_seconds(self._base_delay_ms, self._max_delay_ms, self._backoff_factor, attempt)

    def is_transient(self, exc: Exception) -> bool:
        """Return whether ``exc`` is retryable (transient only)."""
        if isinstance(exc, BrokerTransientError):
            return True
        # I/O style failures are transient; everything else (validation,
        # security, gates, stop blocks) is never retried.
        return isinstance(exc, (ConnectionError, TimeoutError, OSError))

    def run(self, operation: Callable[[], Any]) -> RetryResult:
        """Execute ``operation`` with bounded retry.

        Attempts stop on the first non-transient failure (propagated
        immediately) or when the retry budget is exhausted. After exhaustion
        the last failure is raised as :class:`BrokerRetryExhaustedError` so a
        final failure is always recorded and never converted into a success.
        """
        attempt = 0
        last_error: Exception | None = None
        while attempt < self._max_attempts:
            try:
                value = operation()
            except (BrokerTransientError, ConnectionError, TimeoutError, OSError) as exc:
                last_error = exc
                attempt += 1
                if attempt >= self._max_attempts:
                    break
                delay = self.delay_before_attempt(attempt)
                self._logger.warning(
                    "Retrying operation after transient failure (attempt %d/%d, delay %.2fs): %s",
                    attempt + 1,
                    self._max_attempts,
                    delay,
                    exc,
                )
                self._sleep(delay)
                continue
            except OrderAlreadyExistsError as exc:
                # The operation already produced the record on an earlier
                # attempt whose response was lost; this is an idempotent
                # success, not an error.
                self._logger.info("Idempotent success on retry (order already exists): %s", exc)
                return RetryResult(value=None, attempts=attempt + 1, retried=attempt > 0)
            else:
                return RetryResult(value=value, attempts=attempt + 1, retried=attempt > 0)

        assert last_error is not None  # unreachable when the loop succeeded
        self._logger.error(
            "Operation failed after %d attempt(s); last error: %s",
            self._max_attempts,
            last_error,
        )
        raise BrokerRetryExhaustedError(
            f"operation failed after {self._max_attempts} attempt(s): {last_error}",
            attempts=self._max_attempts,
            last_error=last_error,
        ) from last_error
