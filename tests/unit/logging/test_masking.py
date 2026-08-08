"""Sensitive-data masking tests (ADR-0010 section 5.7).

Verifies that secrets, API keys, tokens, and credentials are masked before
they reach any log handler.
"""

from __future__ import annotations

import logging

import pytest

from aios.config.settings import LoggingSettings
from aios.logging import SensitiveDataFilter, mask_sensitive
from aios.logging.setup import _build_handler

pytestmark = pytest.mark.unit


class TestMaskSensitive:
    @pytest.mark.parametrize(
        "message",
        [
            "connection password=s3cret",
            'password = "hunter2"',
            "login failed: password: pass123",
            'api_key="sk-live-1234567890"',
            "token=eyJhbGciOiJIUzI1NiJ9",
            "authorization: Bearer abc.def.ghi",
            "credential: user:pass",
            "private_key: -----BEGIN PRIVATE KEY-----",
        ],
    )
    def test_masks_sensitive_values(self, message: str) -> None:
        masked = mask_sensitive(message)
        assert "[REDACTED]" in masked

    def test_masks_multiple_values(self) -> None:
        masked = mask_sensitive("password=a secret=another")
        assert masked.count("[REDACTED]") == 2

    def test_leaves_ordinary_text_unchanged(self) -> None:
        message = "portfolio valuation computed successfully"
        assert mask_sensitive(message) == message


class TestSensitiveDataFilter:
    def test_filter_redacts_record(self) -> None:
        record = logging.LogRecord(
            name="aios.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="password=s3cret",
            args=(),
            exc_info=None,
        )
        assert SensitiveDataFilter().filter(record) is True
        assert "[REDACTED]" in str(record.msg)

    def test_emitted_records_are_masked(self) -> None:
        import io

        stream = io.StringIO()
        handler = _build_handler(LoggingSettings())
        handler.stream = stream
        record = logging.LogRecord(
            name="aios.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="api_key=abc123",
            args=(),
            exc_info=None,
        )
        handler.handle(record)
        output = stream.getvalue()
        assert "api_key=[REDACTED]" in output
        assert "abc123" not in output
