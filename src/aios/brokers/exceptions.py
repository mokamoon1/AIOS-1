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
