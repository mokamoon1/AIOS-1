"""Authorized paper-trading broker service (AIOS-408 section 8, AIOS-406 section 13).

The Broker Service wraps a :class:`BrokerInterface` (the Paper Trading
broker in Phase 5) with the documented authorization chain: the caller must
hold the ``SUBMIT_PAPER_ORDERS`` permission (AIOS-408 section 8) and every
paper order must be backed by an approved decision (AIOS-406 section 13,
AIOS-208 sections 5 and 8). Shariah and risk approvals are never bypassed
(AIOS-208 section 9, ADR-0002). No live broker and no production execution
are used (AIOS-208 section 8).

Persistence goes through the injected ``BrokerDataStore`` (the Data Layer
facade) so this module never touches the database directly (AIOS-606 section
1, AIOS-605 section 13). When no store is configured, the broker still
operates in memory and persistence failures degrade with a logged warning
instead of fabricating storage results (mirroring the Decision Engine's
``persisted=False`` degradation).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol

from aios.agents.permissions import Permission, Role, require_permission
from aios.brokers.exceptions import BrokerValidationError
from aios.brokers.interface import BrokerInterface
from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
    PortfolioStatus,
)
from aios.data.models import DecisionAction, InvestmentDecision
from aios.database.exceptions import RecordNotFoundError
from aios.errors import DatabaseError, DataError

_REQUIRED_APPROVALS = (
    "shariah_approval",
    "data_availability",
    "analysis_completion",
    "risk_approval",
)


class BrokerDataStore(Protocol):
    """Persistence facade satisfied by the Data Layer (AIOS-606 section 1).

    The Broker Service reads and writes paper-trading records exclusively
    through this protocol; the concrete DataService implements it.
    """

    def store_paper_order(self, order: PaperOrder) -> PaperOrder: ...

    def get_paper_order(self, order_id: str) -> PaperOrder: ...

    def list_paper_orders(self, *, status: OrderStatus | None = None) -> list[PaperOrder]: ...

    def update_paper_order(self, order: PaperOrder) -> PaperOrder: ...

    def store_paper_fill(self, fill: PaperFill) -> PaperFill: ...

    def list_paper_fills(self, *, order_id: str | None = None) -> list[PaperFill]: ...

    def store_paper_position(self, position: BrokerPosition) -> BrokerPosition: ...

    def list_paper_positions(self) -> list[BrokerPosition]: ...

    def store_broker_account(self, account: BrokerAccount) -> BrokerAccount: ...

    def get_broker_account(self, broker_id: str) -> BrokerAccount: ...


class SimulationBroker(BrokerInterface, Protocol):
    """A broker that supports the explicit paper-fill lifecycle.

    Phase 5 simulates fills deterministically: they are never automatic
    (AIOS-208 section 9). Concrete adapters expose ``fill_order`` and
    ``reject_order`` in addition to the standard broker operations.
    """

    def fill_order(self, order_id: str, *, price: float) -> tuple[PaperOrder, PaperFill]: ...

    def reject_order(self, order_id: str, *, reason: str) -> PaperOrder: ...


def _decision_ref(decision: InvestmentDecision) -> str:
    """Return the audit reference linking an order to its approving decision."""
    return f"{decision.symbol}:{decision.timestamp.isoformat()}"


def decision_to_side(decision: DecisionAction) -> OrderSide | None:
    """Map an actionable decision direction to an order side (AIOS-208 section 5).

    BUY and SELL produce orders; HOLD, WAIT, and NO TRADE are no-action
    decisions that must never create an order (AIOS-208 section 10).
    """
    if decision is DecisionAction.BUY:
        return OrderSide.BUY
    if decision is DecisionAction.SELL:
        return OrderSide.SELL
    return None


class BrokerService:
    """Authorized facade over the paper broker (AIOS-603 section 11).

    ``broker`` is the execution adapter (Paper Trading in Phase 5) and
    ``store`` is the optional Data Layer facade used for persistence.
    """

    def __init__(
        self,
        broker: SimulationBroker,
        *,
        store: BrokerDataStore | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._broker = broker
        self._store = store
        self._logger = logger or logging.getLogger("aios.brokers.service")

    @property
    def broker(self) -> BrokerInterface:
        """Return the underlying broker adapter."""
        return self._broker

    @property
    def store(self) -> BrokerDataStore | None:
        """Return the persistence facade (None until wired)."""
        return self._store

    @property
    def broker_id(self) -> str:
        """Return the underlying broker identifier."""
        return self._broker.broker_id

    # -- execution (AIOS-407 section 4.3) -----------------------------------

    def submit_paper_order(
        self,
        order: PaperOrder,
        *,
        decision: InvestmentDecision,
        role: Role,
    ) -> PaperOrder:
        """Submit a paper order backed by an approved decision (AIOS-406 section 13).

        Enforces, in order:

        1. The caller holds ``SUBMIT_PAPER_ORDERS`` (AIOS-408 section 8).
        2. The order is backed by a valid approved decision carrying Shariah
           and risk approval (AIOS-208 sections 8-9, ADR-0002).
        3. The order matches the approved decision (symbol and side).

        The returned order is in the PENDING state; no auto-fill occurs.
        """
        require_permission(role, Permission.SUBMIT_PAPER_ORDERS)
        self._validate_decision(order, decision)
        order = self._order_with_decision_ref(order, decision)
        submitted = self._broker.submit_order(order)
        self._persist_order(submitted)
        return submitted

    def fill_order(
        self, order_id: str, *, price: float, role: Role
    ) -> tuple[PaperOrder, PaperFill]:
        """Explicitly fill a PENDING paper order at ``price`` (AIOS-1103).

        Requires ``SUBMIT_PAPER_ORDERS``. The fill is recorded and the
        affected order, positions, and account are persisted.
        """
        require_permission(role, Permission.SUBMIT_PAPER_ORDERS)
        filled, fill = self._broker.fill_order(order_id, price=price)
        self._persist_fill(filled, fill)
        return filled, fill

    def cancel_order(self, order_id: str, *, role: Role) -> PaperOrder:
        """Cancel a PENDING paper order (PENDING -> CANCELLED, AIOS-1103)."""
        require_permission(role, Permission.SUBMIT_PAPER_ORDERS)
        cancelled = self._broker.cancel_order(order_id)
        self._persist_order(cancelled)
        return cancelled

    def reject_order(self, order_id: str, *, reason: str, role: Role) -> PaperOrder:
        """Reject a PENDING paper order (PENDING -> REJECTED, AIOS-1103)."""
        require_permission(role, Permission.SUBMIT_PAPER_ORDERS)
        rejected = self._broker.reject_order(order_id, reason=reason)
        self._persist_order(rejected)
        return rejected

    # -- reads ----------------------------------------------------------------

    def get_order(self, order_id: str) -> PaperOrder:
        """Return the paper order identified by ``order_id``."""
        return self._broker.get_order(order_id)

    def list_orders(self) -> list[PaperOrder]:
        """Return all paper orders in submission order."""
        return self._broker.list_orders()

    def get_positions(self) -> list[BrokerPosition]:
        """Return the open positions held at the broker (Get Positions)."""
        return self._broker.get_positions()

    def check_account(self) -> BrokerAccount:
        """Return the account status (Check Account, AIOS-407)."""
        return self._broker.check_account()

    def get_portfolio_status(self) -> PortfolioStatus:
        """Return the portfolio status (Get Portfolio Status, AIOS-407)."""
        return self._broker.get_portfolio_status()

    # -- internals ------------------------------------------------------------

    def _validate_decision(self, order: PaperOrder, decision: InvestmentDecision) -> None:
        """Reject any order not backed by a valid approved decision.

        Implements AIOS-406 section 13 and AIOS-208 sections 8-10: the
        decision must be actionable (BUY/SELL), match the order, and carry
        Shariah and risk approval. Missing or incomplete approval data is
        rejected rather than guessed.
        """
        if decision.symbol != order.symbol:
            raise BrokerValidationError(
                f"Order symbol {order.symbol!r} does not match the approved "
                f"decision symbol {decision.symbol!r}"
            )
        expected_side = decision_to_side(decision.decision)
        if expected_side is None:
            raise BrokerValidationError(
                f"Decision {decision.decision.value!r} is not actionable; "
                "no forced trading is allowed (AIOS-208 section 10)"
            )
        if order.side.value != expected_side.value:
            raise BrokerValidationError(
                f"Order side {order.side.value!r} does not match decision "
                f"{decision.decision.value!r}"
            )
        validation = decision.supporting_data.get("validation")
        if not isinstance(validation, Mapping):
            raise BrokerValidationError(
                "Decision carries no validation approval data; paper order blocked"
            )
        for key in _REQUIRED_APPROVALS:
            if validation.get(key) is not True:
                raise BrokerValidationError(
                    f"Decision is missing approval {key!r}; paper order blocked "
                    "(AIOS-208 section 9)"
                )

    def _order_with_decision_ref(
        self, order: PaperOrder, decision: InvestmentDecision
    ) -> PaperOrder:
        if order.decision_ref is not None:
            return order
        return order.model_copy(update={"decision_ref": _decision_ref(decision)})

    def _persist_order(self, order: PaperOrder) -> None:
        """Persist an order through the store, degrading gracefully when absent."""
        store = self._store
        if store is None:
            self._logger.warning(
                "Broker store not configured; order %s not persisted", order.order_id
            )
            return
        try:
            store.update_paper_order(order)
        except RecordNotFoundError:
            self._persist_new_order(order, store)
        except (DataError, DatabaseError) as exc:
            self._logger.warning("Could not persist paper order %s: %s", order.order_id, exc)

    def _persist_new_order(self, order: PaperOrder, store: BrokerDataStore) -> None:
        """Insert a newly submitted order, logging persistence failures."""
        try:
            store.store_paper_order(order)
        except (DataError, DatabaseError) as exc:
            self._logger.warning("Could not persist new paper order %s: %s", order.order_id, exc)

    def _persist_fill(self, filled: PaperOrder, fill: PaperFill) -> None:
        """Persist a fill plus the resulting order, positions, and account."""
        if self._store is None:
            self._logger.warning("Broker store not configured; fill %s not persisted", fill.fill_id)
            return
        try:
            self._store.store_paper_fill(fill)
            self._store.update_paper_order(filled)
            for position in self._broker.get_positions():
                self._store.store_paper_position(position)
            self._store.store_broker_account(self._broker.check_account())
        except (DataError, DatabaseError) as exc:
            self._logger.warning("Could not persist paper fill %s: %s", fill.fill_id, exc)
