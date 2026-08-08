"""Authority and bypass-path security tests (AIOS-706, AIOS-106, ADR-0002).

Verifies that no component can bypass the documented authority chain:
- Only the Decision Engine may issue recommendations (AIOS-605 section 11).
- Orders require the ``SUBMIT_PAPER_ORDERS`` permission (AIOS-408 section 8).
- Paper orders require Shariah and risk approval (AIOS-106 section 5, AIOS-208).
- Non-actionable decisions never create orders (AIOS-208 section 10).
- Shariah compliance is a hard gate (AIOS-301 FR-002).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from aios.agents.permissions import Role
from aios.brokers.exceptions import BrokerValidationError
from aios.brokers.models import OrderSide, PaperOrder
from aios.brokers.paper import PaperBroker
from aios.brokers.service import BrokerService
from aios.data.models import ComplianceStatus, DecisionAction, InvestmentDecision
from aios.engines.base import DataAccess
from aios.engines.exceptions import EngineValidationError
from aios.engines.roster import ENGINE_CLASSES, create_engine, require_decision_authority
from aios.engines.types import EngineType
from aios.errors import SecurityError

pytestmark = pytest.mark.security


def _approved_decision(symbol: str = "AAPL") -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol,
        decision=DecisionAction.BUY,
        reason="approved test decision",
        confidence=0.8,
        risk_score=0.2,
        supporting_data={
            "validation": {
                "shariah_approval": True,
                "data_availability": True,
                "analysis_completion": True,
                "risk_approval": True,
            }
        },
    )


def _order(side: OrderSide = OrderSide.BUY, symbol: str = "AAPL") -> PaperOrder:
    return PaperOrder(
        order_id=uuid4().hex,
        broker_id="paper",
        symbol=symbol,
        exchange="XNAS",
        side=side,
        quantity=10,
        price=100.0,
    )


class TestDecisionAuthority:
    """Only the Decision Engine issues recommendations (AIOS-605 section 11)."""

    @pytest.mark.parametrize("engine_type", [t for t in EngineType if t is not EngineType.DECISION])
    def test_analysis_engines_cannot_issue_recommendations(self, engine_type: EngineType) -> None:
        engine = create_engine(engine_type)
        with pytest.raises(SecurityError):
            require_decision_authority(engine)

    def test_decision_engine_is_authorized(self) -> None:
        engine = create_engine(EngineType.DECISION)
        require_decision_authority(engine)

    def test_only_decision_engine_declares_authority(self) -> None:
        for engine_type, cls in ENGINE_CLASSES.items():
            declared = cls.can_issue_recommendation
            assert declared is (engine_type is EngineType.DECISION)


class TestOrderAuthorization:
    """Paper orders require permission plus an approved decision (AIOS-408, AIOS-106)."""

    def test_lacking_permission_blocks_order(self) -> None:
        service = BrokerService(PaperBroker("paper", "paper-account"))
        with pytest.raises(SecurityError):
            service.submit_paper_order(_order(), decision=_approved_decision(), role=Role.ANALYST)

    def test_approved_order_submits_with_trading_role(self) -> None:
        service = BrokerService(PaperBroker("paper", "paper-account"))
        submitted = service.submit_paper_order(
            _order(), decision=_approved_decision(), role=Role.TRADING
        )
        assert submitted.status.value == "pending"
        assert submitted.decision_ref is not None

    def test_risk_approval_cannot_be_bypassed(self) -> None:
        """AIOS-106 section 5: the Trading Module must not bypass risk checks."""
        validation = dict(_approved_decision().supporting_data["validation"])
        validation["risk_approval"] = False
        decision = _approved_decision().model_copy(
            update={"supporting_data": {"validation": validation}}
        )
        service = BrokerService(PaperBroker("paper", "paper-account"))
        with pytest.raises(BrokerValidationError, match="risk_approval"):
            service.submit_paper_order(_order(), decision=decision, role=Role.TRADING)

    def test_missing_approval_data_blocks_order(self) -> None:
        decision = InvestmentDecision(
            symbol="AAPL",
            decision=DecisionAction.BUY,
            reason="no approvals recorded",
            confidence=0.7,
        )
        service = BrokerService(PaperBroker("paper", "paper-account"))
        with pytest.raises(BrokerValidationError, match="approval"):
            service.submit_paper_order(_order(), decision=decision, role=Role.TRADING)

    def test_symbol_mismatch_blocks_order(self) -> None:
        service = BrokerService(PaperBroker("paper", "paper-account"))
        with pytest.raises(BrokerValidationError, match="does not match"):
            service.submit_paper_order(
                _order(symbol="AAPL"), decision=_approved_decision("MSFT"), role=Role.TRADING
            )

    def test_non_actionable_decision_never_creates_order(self) -> None:
        """AIOS-208 section 10: HOLD/WAIT/NO TRADE must not produce an order."""
        decision = _approved_decision().model_copy(update={"decision": DecisionAction.WAIT})
        service = BrokerService(PaperBroker("paper", "paper-account"))
        with pytest.raises(BrokerValidationError, match="not actionable"):
            service.submit_paper_order(_order(), decision=decision, role=Role.TRADING)


class TestShariahGate:
    """Only Shariah-approved securities enter analysis (AIOS-301 FR-002)."""

    def test_non_compliant_security_is_blocked(self) -> None:
        class DenyingDataAccess(DataAccess):
            def get_compliance_status(self, symbol, *, as_of=None):
                del as_of
                from datetime import date

                from aios.data.models import ShariahCompliance

                return ShariahCompliance(
                    symbol=symbol,
                    company_name="Blocked Corp",
                    exchange="XNAS",
                    country="US",
                    asset_type="equity",
                    compliance_status=ComplianceStatus.NON_COMPLIANT,
                    provider="test",
                    review_date=date(2026, 1, 1),
                    effective_date=date(2026, 1, 1),
                    screening_methodology="test",
                    screening_date=date(2026, 1, 1),
                )

        engine = create_engine(EngineType.TECHNICAL, data_access=DenyingDataAccess())
        with pytest.raises(EngineValidationError, match="not Shariah-approved"):
            engine.require_compliant("AAPL")
