"""Kill switch integration tests (Phase 9.6, P0-2).

Proves the emergency stop is wired into the actual paper order submission
path: while stopped, every new order is rejected with the stop reason; after
acknowledge + clear, orders flow again provided all existing gates pass.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aios.agents.permissions import Role
from aios.brokers.exceptions import TradeBlockedError
from aios.brokers.guards import EmergencyStopGuard, GuardChain
from aios.brokers.models import OrderSide, OrderStatus, PaperOrder
from aios.brokers.paper import PaperBroker
from aios.brokers.service import BrokerService
from aios.config.settings import MonitoringSettings
from aios.data.models import DecisionAction, InvestmentDecision
from aios.monitoring.emergency_stop import EmergencyStopManager, StopReason
from aios.monitoring.event_log import EVENT_EMERGENCY_CLEAR, EVENT_EMERGENCY_STOP, EventLog

pytestmark = pytest.mark.unit

_UTC = timezone.utc


def _stop_manager(event_log: EventLog | None = None) -> EmergencyStopManager:
    """Build a stop manager with a settings stub (no env dependency)."""

    class _Settings:
        monitoring = MonitoringSettings()

    return EmergencyStopManager(settings=_Settings(), event_log=event_log)


def _decision(symbol: str = "AAPL") -> InvestmentDecision:
    return InvestmentDecision(
        symbol=symbol,
        decision=DecisionAction.BUY,
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


def _order(broker: PaperBroker, *, symbol: str = "AAPL") -> PaperOrder:
    return PaperOrder(
        order_id="ord-stop-1",
        broker_id=broker.broker_id,
        symbol=symbol,
        exchange="NASDAQ",
        side=OrderSide.BUY,
        quantity=10.0,
        price=100.0,
    )


class TestKillSwitchIntegration:
    def test_stopped_submit_is_rejected_with_reason(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        stop = _stop_manager(EventLog())
        chain = GuardChain([EmergencyStopGuard(stop)])
        service = BrokerService(broker, guards=chain)
        stop.trigger_stop(StopReason.SYSTEM_ERROR, "risk_engine")

        with pytest.raises(TradeBlockedError) as exc_info:
            service.submit_paper_order(_order(broker), decision=_decision(), role=Role.TRADING)
        assert exc_info.value.code == "emergency_stop"
        assert "emergency stop active" in str(exc_info.value)
        assert "system_error" in exc_info.value.reason
        # No order reaches the broker while stopped.
        assert broker.list_orders() == []

    def test_stopped_blocks_fill_cancel_reject_too(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        stop = _stop_manager(EventLog())
        service = BrokerService(broker, guards=GuardChain([EmergencyStopGuard(stop)]))
        service.submit_paper_order(_order(broker), decision=_decision(), role=Role.TRADING)
        stop.trigger_stop(StopReason.MANUAL_OVERRIDE, "compliance")

        for operation in (
            lambda: service.fill_order("ord-stop-1", price=100.0, role=Role.TRADING),
            lambda: service.cancel_order("ord-stop-1", role=Role.TRADING),
            lambda: service.reject_order("ord-stop-1", reason="x", role=Role.TRADING),
        ):
            with pytest.raises(TradeBlockedError):
                operation()
        # The order remains PENDING; the stop blocked every transition.
        assert broker.get_order("ord-stop-1").status is OrderStatus.PENDING

    def test_clear_allows_order_to_flow_through_all_gates(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        stop = _stop_manager(EventLog())
        service = BrokerService(broker, guards=GuardChain([EmergencyStopGuard(stop)]))
        stop.trigger_stop(StopReason.MANUAL, "ops")

        with pytest.raises(TradeBlockedError):
            service.submit_paper_order(_order(broker), decision=_decision(), role=Role.TRADING)

        stop.acknowledge_stop("operator")
        stop.clear_stop("operator")
        assert stop.is_stopped is False

        submitted = service.submit_paper_order(_order(broker), decision=_decision(), role=Role.TRADING)
        assert submitted.status is OrderStatus.PENDING
        # Gates still enforced after clearing: a bad decision is still blocked.
        missing_shariah = _decision()
        missing_shariah = missing_shariah.model_copy(
            update={
                "supporting_data": {
                    "validation": {
                        "shariah_approval": False,
                        "data_availability": True,
                        "analysis_completion": True,
                        "risk_approval": True,
                    }
                }
            }
        )
        from aios.brokers.exceptions import BrokerValidationError

        with pytest.raises(BrokerValidationError):
            service.submit_paper_order(_order(broker, symbol="MSFT"), decision=missing_shariah, role=Role.TRADING)

    def test_guard_chain_empty_allows_submission(self) -> None:
        broker = PaperBroker("bkr-1", "acc-1")
        service = BrokerService(broker, guards=GuardChain([]))
        submitted = service.submit_paper_order(_order(broker), decision=_decision(), role=Role.TRADING)
        assert submitted.status is OrderStatus.PENDING


class TestKillSwitchAuditEvents:
    def test_stop_and_clear_record_audit_events(self) -> None:
        log = EventLog()
        stop = _stop_manager(log)
        stop.trigger_stop(StopReason.SHARIAH_VIOLATION, "shariah_gate")
        assert log.count_in_window(EVENT_EMERGENCY_STOP, 60) == 1
        entry = log.latest(EVENT_EMERGENCY_STOP)
        assert entry.payload["reason"] == "shariah_violation"
        assert entry.payload["triggered_by"] == "shariah_gate"

        stop.acknowledge_stop("ops")
        stop.clear_stop("ops")
        assert log.count_in_window(EVENT_EMERGENCY_CLEAR, 60) == 1

