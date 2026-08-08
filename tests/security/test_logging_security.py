"""Logging security tests (ADR-0010 section 5.7, AIOS-706 section 10).

Logs must never expose secrets, API keys, tokens, or credentials. These tests
verify the masking filter and JSON formatter redact sensitive values, and
that ERROR events published to the Event Bus are masked as well.
"""

from __future__ import annotations

import io
import logging

import pytest

from aios.errors.publisher import ErrorEventPublisher
from aios.events import InMemoryEventBus
from aios.logging.formatters import JsonFormatter
from aios.logging.masking import SensitiveDataFilter, mask_sensitive

pytestmark = pytest.mark.security


def _json_logger(stream: io.StringIO) -> logging.Logger:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SensitiveDataFilter())
    logger = logging.getLogger("aios.security.logging.test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


class TestMasking:
    @pytest.mark.parametrize(
        ("message", "secret"),
        [
            ("connection password=hunter2 established", "hunter2"),
            ("token=abc123def456", "abc123def456"),
            ("api_key=sk_live_0123456789abcdef", "sk_live_0123456789abcdef"),
            ('credential: "admin:passw0rd"', "admin:passw0rd"),
        ],
    )
    def test_mask_sensitive_redacts_value(self, message: str, secret: str) -> None:
        masked = mask_sensitive(message)
        assert secret not in masked
        assert "[REDACTED]" in masked

    def test_plain_message_is_unchanged(self) -> None:
        assert mask_sensitive("order filled for AAPL") == "order filled for AAPL"


class TestLogOutput:
    def test_json_logs_do_not_expose_secret(self) -> None:
        stream = io.StringIO()
        logger = _json_logger(stream)
        logger.info("auth failure: password=supersecret token=tok123")
        output = stream.getvalue()
        assert "supersecret" not in output
        assert "tok123" not in output
        assert "[REDACTED]" in output

    def test_json_log_contains_correlation_fields(self) -> None:
        from aios.logging.correlation import correlation_scope

        stream = io.StringIO()
        logger = _json_logger(stream)
        with correlation_scope(request_id="req-1", trace_id="trace-9"):
            logger.info("analysis complete")
        output = stream.getvalue()
        assert '"request_id": "req-1"' in output
        assert '"trace_id": "trace-9"' in output


class TestErrorEventMasking:
    async def test_error_event_message_is_masked(self) -> None:
        bus = InMemoryEventBus()
        seen = []

        async def record(event) -> None:
            seen.append(event)

        bus.subscribe("ERROR", record)
        await ErrorEventPublisher(bus).publish(
            source="data",
            component="DataPipeline",
            error_type="ProviderError",
            message="connect failed with api_key=sk_live_abcdef0123456789",
        )
        assert len(seen) == 1
        payload = seen[0].payload
        assert "sk_live_abcdef0123456789" not in payload["message"]
        assert "[REDACTED]" in payload["message"]
