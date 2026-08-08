"""Decision-to-broker wiring (AIOS-406 section 13, AIOS-603 section 11).

The :class:`PaperOrderCoordinator` routes an approved investment decision to
the Paper Broker through the authorized :class:`BrokerService`. The flow is
strict: the latest decision for a symbol is read, it must be actionable
(BUY/SELL) and carry every documented approval, and submission requires the
``SUBMIT_PAPER_ORDERS`` permission (AIOS-408 section 8). No arbitrary agent
executes orders and no live broker is used (AIOS-208 section 8).

No position-sizing rule is invented here: the quantity and price are explicit
caller-supplied inputs, because sizing and price rules remain configurable
placeholders (AIOS-406 sections 6-7).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import uuid4

from aios.agents.permissions import Role
from aios.brokers.exceptions import BrokerValidationError
from aios.brokers.models import PaperOrder
from aios.brokers.service import BrokerService, decision_to_side
from aios.data.models import InvestmentDecision


class PaperOrderDecisionReader(Protocol):
    """Read interface satisfied by the Data Layer facade (AIOS-501 section 2)."""

    def get_latest_decision(self, symbol: str) -> InvestmentDecision: ...


class PaperOrderCoordinator:
    """Submits paper orders only for approved, actionable decisions (AIOS-406 section 13).

    ``service`` is the authorized broker facade and ``reader`` supplies the
    latest decision for a symbol; the Data Service implements ``reader``.
    """

    def __init__(
        self,
        service: BrokerService,
        reader: PaperOrderDecisionReader,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._service = service
        self._reader = reader
        self._logger = logger or logging.getLogger("aios.brokers.coordinator")

    @property
    def service(self) -> BrokerService:
        """Return the underlying authorized broker service."""
        return self._service

    def submit_for_decision(
        self,
        symbol: str,
        *,
        exchange: str,
        quantity: float,
        price: float,
        role: Role,
    ) -> PaperOrder:
        """Submit a paper order backed by the latest approved decision.

        The decision must be actionable (BUY/SELL) — HOLD, WAIT, and NO TRADE
        never create an order (AIOS-208 section 10). The order side is taken
        from the approved decision; the symbol, exchange, quantity, and price
        are explicit caller inputs. Submission enforces ``SUBMIT_PAPER_ORDERS``
        and all four decision approval gates (AIOS-408 section 8, AIOS-406
        section 13).
        """
        decision = self._reader.get_latest_decision(symbol)
        side = decision_to_side(decision.decision)
        if side is None:
            raise BrokerValidationError(
                f"Latest decision for {symbol!r} is {decision.decision.value!r} "
                "(not actionable); no forced trading is allowed (AIOS-208 section 10)"
            )
        order = PaperOrder(
            order_id=uuid4().hex,
            broker_id=self._service.broker_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
        )
        submitted = self._service.submit_paper_order(order, decision=decision, role=role)
        self._logger.info(
            "Paper order %s routed for %s from approved %s decision",
            submitted.order_id,
            symbol,
            submitted.side.value,
        )
        return submitted
