"""PaperOrderCoordinator decision-routing tests (AIOS-406 section 13)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios.agents.permissions import Role
from aios.brokers.coordinator import PaperOrderCoordinator, PaperOrderDecisionReader
from aios.brokers.exceptions import BrokerValidationError
from aios.brokers.models import OrderStatus
from aios.brokers.paper import PaperBroker
from aios.brokers.service import BrokerService
from aios.data.models import DecisionAction, InvestmentDecision
from aios.errors import SecurityError

pytestmark = pytest.mark.unit

_UTC = timezone.utc


def _decision(
    symbol: str = "AAPL", decision: DecisionAction = DecisionAction.BUY
) -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol,
        decision=decision,
        reason="approved",
        confidence=1.0,
        risk_score=0.2,
        timestamp=datetime(2026, 8, 1, 12, 0, tzinfo=_UTC),
        supporting_data={
            "validation": {
                "shariah_approval": True,
                "data_availability": True,
                "analysis_completion": True,
                "risk_approval": True,
            }
        },
    )


class _StaticReader(PaperOrderDecisionReader):
    def __init__(self, decision: InvestmentDecision) -> None:
        self._decision = decision

    def get_latest_decision(self, symbol: str) -> InvestmentDecision:
        return self._decision


class TestPaperOrderCoordinator:
    def _coordinator(
        self, decision: InvestmentDecision
    ) -> tuple[PaperOrderCoordinator, PaperBroker]:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker)
        return PaperOrderCoordinator(service, _StaticReader(decision)), broker

    def test_submits_buy_order_from_approved_decision(self) -> None:
        coordinator, broker = self._coordinator(_decision())
        order = coordinator.submit_for_decision(
            "AAPL", exchange="NASDAQ", quantity=10.0, price=100.0, role=Role.TRADING
        )
        assert order.status is OrderStatus.PENDING
        assert order.symbol == "AAPL"
        assert order.exchange == "NASDAQ"
        assert order.quantity == 10.0
        assert order.price == 100.0
        assert order.broker_id == "bkr-1"
        assert order.decision_ref is not None
        assert broker.get_order(order.order_id).status is OrderStatus.PENDING

    def test_submits_sell_order_from_approved_decision(self) -> None:
        coordinator, _ = self._coordinator(_decision(decision=DecisionAction.SELL))
        order = coordinator.submit_for_decision(
            "AAPL", exchange="NASDAQ", quantity=5.0, price=110.0, role=Role.TRADING
        )
        assert order.side.value == "sell"

    def test_requires_submit_permission(self) -> None:
        coordinator, _ = self._coordinator(_decision())
        with pytest.raises(SecurityError):
            coordinator.submit_for_decision(
                "AAPL", exchange="NASDAQ", quantity=10.0, price=100.0, role=Role.ANALYST
            )

    @pytest.mark.parametrize(
        "action",
        [DecisionAction.WAIT, DecisionAction.HOLD, DecisionAction.NO_TRADE],
    )
    def test_non_actionable_decision_never_submits(self, action: DecisionAction) -> None:
        coordinator, broker = self._coordinator(_decision(decision=action))
        with pytest.raises(BrokerValidationError):
            coordinator.submit_for_decision(
                "AAPL", exchange="NASDAQ", quantity=10.0, price=100.0, role=Role.TRADING
            )
        assert broker.list_orders() == []

    def test_unapproved_decision_blocked_by_service(self) -> None:
        unapproved = _decision().model_copy(
            update={
                "supporting_data": {
                    "validation": {
                        "shariah_approval": True,
                        "data_availability": True,
                        "analysis_completion": True,
                        "risk_approval": False,
                    }
                }
            }
        )
        coordinator, broker = self._coordinator(unapproved)
        with pytest.raises(BrokerValidationError):
            coordinator.submit_for_decision(
                "AAPL", exchange="NASDAQ", quantity=10.0, price=100.0, role=Role.TRADING
            )
        assert broker.list_orders() == []
