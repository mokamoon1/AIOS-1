"""Broker interface (AIOS-407 section 4.3, AIOS-1103 section 13).

The Broker Interface abstracts the documented broker operations (AIOS-407
section 4.3): Check Account, Submit Paper Order, Get Positions, and Get
Portfolio Status, together with order cancellation and order status lookup
(AIOS-603 section 11). Phase 5 implements Paper Trading only (AIOS-101
section 4.6); live brokers are out of scope.

Order lifecycle transitions are explicit methods on the concrete simulation
adapter; the interface never auto-fills and no slippage, fee, or latency
model is introduced (AIOS-208 section 9).
"""

from __future__ import annotations

from typing import Protocol

from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    PaperOrder,
    PortfolioStatus,
)


class BrokerInterface(Protocol):
    """Standard broker operations (AIOS-407 section 4.3, AIOS-603 section 11).

    Operations:

    * Check Account (``check_account``).
    * Submit Paper Order (``submit_order``).
    * Cancel Order (``cancel_order``).
    * Order status and listing (``get_order``, ``list_orders``).
    * Get Positions (``get_positions``).
    * Get Portfolio Status (``get_portfolio_status``).
    """

    @property
    def broker_id(self) -> str:
        """Return the stable broker identifier used for registration."""
        ...

    def check_account(self) -> BrokerAccount:
        """Return the current account status (AIOS-407 section 4.3)."""
        ...

    def submit_order(self, order: PaperOrder) -> PaperOrder:
        """Submit a paper order and return it in the PENDING state."""
        ...

    def cancel_order(self, order_id: str) -> PaperOrder:
        """Cancel a PENDING paper order and return it in the CANCELLED state."""
        ...

    def get_order(self, order_id: str) -> PaperOrder:
        """Return the order identified by ``order_id``."""
        ...

    def list_orders(self) -> list[PaperOrder]:
        """Return all submitted orders in submission order."""
        ...

    def get_positions(self) -> list[BrokerPosition]:
        """Return the open positions held at the broker."""
        ...

    def get_portfolio_status(self) -> PortfolioStatus:
        """Return the portfolio/account status (AIOS-407 section 4.3)."""
        ...
