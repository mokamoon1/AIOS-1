"""Retry policy tests (Phase 9.6, P0-4)."""

from __future__ import annotations

import pytest

from aios.agents.permissions import Role
from aios.brokers.exceptions import (
    BrokerRetryExhaustedError,
    BrokerTransientError,
    BrokerValidationError,
    OrderAlreadyExistsError,
)
from aios.brokers.retry import RetryPolicy

pytestmark = pytest.mark.unit


class _Noop:
    def __call__(self, delay: float) -> None:
        self.last_delay = delay


class TestRetryPolicy:
    def test_success_on_first_attempt(self) -> None:
        policy = RetryPolicy(max_attempts=3, sleep_fn=lambda d: None)
        result = policy.run(lambda: "ok")
        assert result.value == "ok"
        assert result.attempts == 1
        assert result.retried is False

    def test_success_after_transient_failures(self) -> None:
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            if calls["count"] < 3:
                raise BrokerTransientError("temporary outage")
            return "recovered"

        noop = _Noop()
        policy = RetryPolicy(max_attempts=5, sleep_fn=noop)
        result = policy.run(operation)
        assert result.value == "recovered"
        assert result.attempts == 3
        assert result.retried is True
        assert noop.last_delay == pytest.approx(0.8)  # 200ms * 2^2 = 800ms

    def test_exhaustion_raises_retry_exhausted(self) -> None:
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            raise BrokerTransientError("persistent outage")

        policy = RetryPolicy(max_attempts=3, sleep_fn=lambda d: None)
        with pytest.raises(BrokerRetryExhaustedError) as exc_info:
            policy.run(operation)
        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_error, BrokerTransientError)
        assert calls["count"] == 3

    def test_exhaustion_records_attempt_count(self) -> None:
        policy = RetryPolicy(max_attempts=4, sleep_fn=lambda d: None)
        with pytest.raises(BrokerRetryExhaustedError) as exc_info:
            policy.run(lambda: (_ for _ in ()).throw(BrokerTransientError("nope")))
        assert exc_info.value.attempts == 4

    def test_validation_error_never_retried(self) -> None:
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            raise BrokerValidationError("invalid order")

        policy = RetryPolicy(max_attempts=3, sleep_fn=lambda d: None)
        with pytest.raises(BrokerValidationError):
            policy.run(operation)
        assert calls["count"] == 1

    def test_transient_connection_error_retried(self) -> None:
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionError("network dropped")
            return "ok"

        policy = RetryPolicy(max_attempts=3, sleep_fn=lambda d: None)
        result = policy.run(operation)
        assert result.value == "ok"
        assert result.retried is True

    def test_order_already_exists_is_idempotent_success(self) -> None:
        def operation():
            raise OrderAlreadyExistsError("order ord-1 already exists")

        policy = RetryPolicy(max_attempts=3, sleep_fn=lambda d: None)
        result = policy.run(operation)
        assert result.value is None
        assert result.attempts == 1

    def test_delay_grows_exponentially_and_is_bounded(self) -> None:
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=100,
            max_delay_ms=500,
            backoff_factor=2.0,
        )
        delays = [policy.delay_before_attempt(i) for i in (0, 1, 2, 3)]
        assert delays == [0.1, 0.2, 0.4, 0.5]  # 0.8 capped to 0.5

    def test_is_transient_classification(self) -> None:
        policy = RetryPolicy()
        assert policy.is_transient(BrokerTransientError("x")) is True
        assert policy.is_transient(ConnectionError("x")) is True
        assert policy.is_transient(TimeoutError("x")) is True
        assert policy.is_transient(OSError("x")) is True
        assert policy.is_transient(BrokerValidationError("x")) is False
        assert policy.is_transient(RuntimeError("x")) is False

    def test_invalid_configuration_rejected(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(max_attempts=0)
        with pytest.raises(ValueError):
            RetryPolicy(backoff_factor=1.0)
        with pytest.raises(ValueError):
            RetryPolicy(base_delay_ms=500, max_delay_ms=100)

    def test_from_settings_uses_config(self) -> None:
        class _Trading:
            retry_max_attempts = 5
            retry_base_delay_ms = 100
            retry_max_delay_ms = 1000
            retry_backoff_factor = 3.0

        policy = RetryPolicy.from_settings(_Trading())
        assert policy.max_attempts == 5
        assert policy.delay_before_attempt(1) == pytest.approx(0.3)


class TestRetryOnBrokerService:
    def test_service_submit_retries_transient_failure(self) -> None:
        from datetime import datetime, timezone

        from aios.agents.permissions import Role
        from aios.brokers.models import OrderSide, PaperOrder
        from aios.brokers.paper import PaperBroker
        from aios.brokers.service import BrokerService
        from aios.data.models import DecisionAction, InvestmentDecision

        decision = InvestmentDecision(
            symbol="AAPL",
            decision=DecisionAction.BUY,
            reason="ok",
            confidence=1.0,
            risk_score=0.2,
            timestamp=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
            supporting_data={
                "validation": {
                    "shariah_approval": True,
                    "data_availability": True,
                    "analysis_completion": True,
                    "risk_approval": True,
                }
            },
        )

        class _FlakyBroker(PaperBroker):
            def __init__(self) -> None:
                super().__init__("bkr-1", "acc-1")
                self._attempts = 0

            def submit_order(self, order: PaperOrder) -> PaperOrder:
                self._attempts += 1
                if self._attempts == 1:
                    raise BrokerTransientError("simulated broker outage")
                return super().submit_order(order)

        broker = _FlakyBroker()
        service = BrokerService(broker, retry_policy=RetryPolicy(max_attempts=3))
        order = PaperOrder(
            order_id="ord-retry-1",
            broker_id=broker.broker_id,
            symbol="AAPL",
            exchange="NASDAQ",
            side=OrderSide.BUY,
            quantity=10.0,
            price=100.0,
        )
        submitted = service.submit_paper_order(order, decision=decision, role=Role.TRADING)
        assert submitted.status.value == "pending"
        assert broker._attempts == 2

    def test_service_submit_exhaustion_propagates(self) -> None:
        from aios.brokers.paper import PaperBroker
        from aios.brokers.service import BrokerService

        class _FlakyBroker(PaperBroker):
            def submit_order(self, order):
                raise BrokerTransientError("simulated persistent outage")

        broker = _FlakyBroker("bkr-1", "acc-1")
        service = BrokerService(broker, retry_policy=RetryPolicy(max_attempts=2))
        from aios.brokers.models import OrderSide, PaperOrder

        order = PaperOrder(
            order_id="ord-retry-2",
            broker_id=broker.broker_id,
            symbol="AAPL",
            exchange="NASDAQ",
            side=OrderSide.BUY,
            quantity=10.0,
            price=100.0,
        )
        with pytest.raises(BrokerRetryExhaustedError):
            service.submit_paper_order(order, decision=_decision(), role=Role.TRADING)


def _decision():
    from datetime import datetime, timezone

    from aios.data.models import DecisionAction, InvestmentDecision

    return InvestmentDecision(
        symbol="AAPL",
        decision=DecisionAction.BUY,
        reason="ok",
        confidence=1.0,
        risk_score=0.2,
        timestamp=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
        supporting_data={
            "validation": {
                "shariah_approval": True,
                "data_availability": True,
                "analysis_completion": True,
                "risk_approval": True,
            }
        },
    )
