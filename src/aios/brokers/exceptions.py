"""Broker module exceptions (AIOS-101 section 4.6, AIOS-208 section 9).

Paper-order lifecycle failures and execution-authorization failures raise
these typed errors so callers can react without guessing why a paper order
was not accepted.
"""

from __future__ import annotations


class BrokerError(Exception):
    """Base class for Broker module errors."""


class BrokerValidationError(BrokerError):
    """Raised when a paper order or execution request is invalid.

    Covers order requests that are not backed by an approved decision, do not
    match the approved decision, or fail recorded-data feasibility checks
    (AIOS-208 sections 8-9).
    """


class BrokerConfigurationError(BrokerError):
    """Raised when a broker service is misconfigured.

    For example when a required data store or broker implementation is
    missing (AIOS-603 section 11, AIOS-606 section 1).
    """


class OrderNotFoundError(BrokerError):
    """Raised when an unknown ``order_id`` is referenced."""


class OrderAlreadyExistsError(BrokerError):
    """Raised when an ``order_id`` is submitted a second time."""


class InvalidOrderStateError(BrokerError):
    """Raised for invalid order lifecycle transitions.

    The documented lifecycle only allows PENDING -> FILLED, PENDING ->
    CANCELLED, and PENDING -> REJECTED (AIOS-1103 section 11); every other
    transition is rejected.
    """


class TradeBlockedError(BrokerError):
    """Raised when a trade guard blocks order submission or execution.

    Raised by the emergency stop / kill switch (``code="emergency_stop"``)
    and by the market-session guard (``code="market_closed"``). The reason
    is always surfaced so operators can react without guessing.
    """

    def __init__(self, message: str, *, code: str = "blocked", reason: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason or message


class BrokerTransientError(BrokerError):
    """Raised when a broker operation fails transiently.

    Transient failures (connection drops, timeouts) are eligible for the
    bounded retry policy. Validation, security, and gate failures are never
    raised as transient.
    """


class BrokerRetryExhaustedError(BrokerError):
    """Raised when a broker operation exhausts the retry budget.

    Carries the number of attempts made and the last underlying error so the
    final failure is never silently converted into a fabricated success.
    """

    def __init__(self, message: str, *, attempts: int, last_error: Exception) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error
