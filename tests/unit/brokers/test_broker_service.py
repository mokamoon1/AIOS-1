"""BrokerService authorization and decision-approval tests (AIOS-408, AIOS-406 section 13)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios.agents.permissions import Role
from aios.brokers.exceptions import BrokerValidationError
from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
)
from aios.brokers.paper import PaperBroker
from aios.brokers.service import BrokerDataStore, BrokerService
from aios.data.models import DecisionAction, InvestmentDecision
from aios.database.exceptions import RecordNotFoundError
from aios.errors import SecurityError

pytestmark = pytest.mark.unit

_UTC = timezone.utc


def _approved_decision(
    symbol: str = "AAPL",
    decision: DecisionAction = DecisionAction.BUY,
    *,
    approvals: dict[str, bool] | None = None,
) -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol,
        decision=decision,
        reason="approved",
        confidence=1.0,
        risk_score=0.2,
        timestamp=datetime(2026, 8, 1, 12, 0, tzinfo=_UTC),
        supporting_data={
            "validation": approvals
            or {
                "shariah_approval": True,
                "data_availability": True,
                "analysis_completion": True,
                "risk_approval": True,
            }
        },
    )


def _order(
    broker: PaperBroker,
    *,
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 10.0,
    price: float = 100.0,
) -> PaperOrder:
    return PaperOrder(
        order_id="ord-1",
        broker_id=broker.broker_id,
        symbol=symbol,
        exchange="NASDAQ",
        side=side,
        quantity=quantity,
        price=price,
    )


class _MemoryStore(BrokerDataStore):
    """In-memory store recording every persistence call for assertions."""

    def __init__(self) -> None:
        self.orders: list[PaperOrder] = []
        self.fills: list[PaperFill] = []
        self.positions: list[BrokerPosition] = []
        self.accounts: list[BrokerAccount] = []

    def store_paper_order(self, order: PaperOrder) -> PaperOrder:
        self.orders.append(order)
        return order

    def get_paper_order(self, order_id: str) -> PaperOrder:
        raise NotImplementedError

    def list_paper_orders(self, *, status: OrderStatus | None = None) -> list[PaperOrder]:
        raise NotImplementedError

    def update_paper_order(self, order: PaperOrder) -> PaperOrder:
        for index, stored in enumerate(self.orders):
            if stored.order_id == order.order_id:
                self.orders[index] = order
                return order
        raise RecordNotFoundError(f"No paper order with id {order.order_id!r}")

    def store_paper_fill(self, fill: PaperFill) -> PaperFill:
        self.fills.append(fill)
        return fill

    def list_paper_fills(self, *, order_id: str | None = None) -> list[PaperFill]:
        raise NotImplementedError

    def store_paper_position(self, position: BrokerPosition) -> BrokerPosition:
        self.positions.append(position)
        return position

    def list_paper_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError

    def store_broker_account(self, account: BrokerAccount) -> BrokerAccount:
        self.accounts.append(account)
        return account

    def get_broker_account(self, broker_id: str) -> BrokerAccount:
        raise NotImplementedError


class TestBrokerService:
    def test_submit_requires_paper_trading_permission(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        with pytest.raises(SecurityError):
            service.submit_paper_order(
                _order(broker), decision=_approved_decision(), role=Role.ANALYST
            )

    def test_submit_with_trading_role_persists_pending_order(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        store = _MemoryStore()
        service = BrokerService(broker, store=store)
        decision = _approved_decision()
        submitted = service.submit_paper_order(_order(broker), decision=decision, role=Role.TRADING)
        assert submitted.status is OrderStatus.PENDING
        assert submitted.decision_ref == "AAPL:2026-08-01T12:00:00+00:00"
        assert len(store.orders) == 1
        assert store.orders[0].order_id == "ord-1"
        assert broker.check_account().cash == 100_000.0

    def test_submit_non_actionable_decision_blocked(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        with pytest.raises(BrokerValidationError):
            service.submit_paper_order(
                _order(broker),
                decision=_approved_decision(decision=DecisionAction.WAIT),
                role=Role.TRADING,
            )

    def test_submit_symbol_mismatch_blocked(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        with pytest.raises(BrokerValidationError):
            service.submit_paper_order(
                _order(broker, symbol="MSFT"),
                decision=_approved_decision(symbol="AAPL"),
                role=Role.TRADING,
            )

    def test_submit_side_mismatch_blocked(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        with pytest.raises(BrokerValidationError):
            service.submit_paper_order(
                _order(broker, side=OrderSide.SELL),
                decision=_approved_decision(),
                role=Role.TRADING,
            )

    def test_submit_missing_approval_blocked(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        missing_risk = _approved_decision(approvals={"risk_approval": False})
        with pytest.raises(BrokerValidationError):
            service.submit_paper_order(_order(broker), decision=missing_risk, role=Role.TRADING)

    def test_submit_keeps_decision_reference_when_present(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        order = _order(broker)
        order = order.model_copy(update={"decision_ref": "already-ref"})
        submitted = service.submit_paper_order(
            order, decision=_approved_decision(), role=Role.TRADING
        )
        assert submitted.decision_ref == "already-ref"

    def test_fill_requires_permission_and_persists_execution(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        store = _MemoryStore()
        service = BrokerService(broker, store=store)
        service.submit_paper_order(_order(broker), decision=_approved_decision(), role=Role.TRADING)
        with pytest.raises(SecurityError):
            service.fill_order("ord-1", price=100.0, role=Role.ANALYST)
        filled, fill = service.fill_order("ord-1", price=100.0, role=Role.TRADING)
        assert filled.status is OrderStatus.FILLED
        assert fill.order_id == "ord-1"
        assert len(store.fills) == 1
        assert len(store.positions) == 1
        assert len(store.accounts) == 1
        assert store.orders[-1].status is OrderStatus.FILLED

    def test_fill_without_store_degrades_gracefully(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        service.submit_paper_order(_order(broker), decision=_approved_decision(), role=Role.TRADING)
        filled, _ = service.fill_order("ord-1", price=100.0, role=Role.TRADING)
        assert filled.status is OrderStatus.FILLED

    def test_cancel_requires_permission(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        service.submit_paper_order(_order(broker), decision=_approved_decision(), role=Role.TRADING)
        with pytest.raises(SecurityError):
            service.cancel_order("ord-1", role=Role.ANALYST)
        cancelled = service.cancel_order("ord-1", role=Role.TRADING)
        assert cancelled.status is OrderStatus.CANCELLED

    def test_reject_requires_permission_and_reason(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        store = _MemoryStore()
        service = BrokerService(broker, store=store)
        service.submit_paper_order(_order(broker), decision=_approved_decision(), role=Role.TRADING)
        with pytest.raises(SecurityError):
            service.reject_order("ord-1", reason="no", role=Role.ANALYST)
        rejected = service.reject_order("ord-1", reason="compliance", role=Role.TRADING)
        assert rejected.status is OrderStatus.REJECTED
        assert store.orders[-1].status is OrderStatus.REJECTED
