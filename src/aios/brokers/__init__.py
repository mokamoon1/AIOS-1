"""AIOS Broker module (AIOS-603 section 11, AIOS-407 section 4.3).

Responsible for order submission, position synchronization, account
information, and order status. The first production stage is Paper Trading
only (AIOS-603 section 11); no live broker or external SDK is wired in this
phase (AIOS-101 section 4.6).
"""

from __future__ import annotations

from aios.brokers.coordinator import PaperOrderCoordinator, PaperOrderDecisionReader
from aios.brokers.exceptions import (
    BrokerConfigurationError,
    BrokerError,
    BrokerValidationError,
    InvalidOrderStateError,
    OrderAlreadyExistsError,
    OrderNotFoundError,
)
from aios.brokers.interface import BrokerInterface
from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
    PerformanceSnapshot,
    PortfolioStatus,
)
from aios.brokers.paper import DEFAULT_PAPER_INITIAL_CASH, PaperBroker
from aios.brokers.service import BrokerDataStore, BrokerService

__all__ = [
    "BrokerAccount",
    "BrokerConfigurationError",
    "BrokerDataStore",
    "BrokerError",
    "BrokerInterface",
    "BrokerPosition",
    "BrokerService",
    "BrokerValidationError",
    "DEFAULT_PAPER_INITIAL_CASH",
    "InvalidOrderStateError",
    "OrderAlreadyExistsError",
    "OrderNotFoundError",
    "OrderSide",
    "OrderStatus",
    "PaperBroker",
    "PaperFill",
    "PaperOrder",
    "PaperOrderCoordinator",
    "PaperOrderDecisionReader",
    "PerformanceSnapshot",
    "PortfolioStatus",
]
