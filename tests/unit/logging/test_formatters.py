"""Log formatter tests (ADR-0010 section 5.2).

Verifies the human-readable formatter (Development/Testing) and the
machine-readable JSON formatter (Paper/Production).
"""

from __future__ import annotations

import json
import logging

import pytest

from aios.logging import HumanReadableFormatter, JsonFormatter, correlation_scope

pytestmark = pytest.mark.unit


def _record(message: str = "hello", exc_info: tuple | None = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="aios.events",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


class TestJsonFormatter:
    def test_emits_parseable_json(self) -> None:
        payload = json.loads(JsonFormatter().format(_record()))
        assert payload["level"] == "WARNING"
        assert payload["component"] == "aios.events"
        assert payload["message"] == "hello"
        assert "timestamp" in payload

    def test_includes_correlation_identifiers(self) -> None:
        with correlation_scope(request_id="req-1", event_id="evt-1"):
            payload = json.loads(JsonFormatter().format(_record()))
        assert payload["request_id"] == "req-1"
        assert payload["event_id"] == "evt-1"
        assert "trace_id" not in payload

    def test_includes_exception(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            exc_record = _record("failed")
            exc_record.exc_info = __import__("sys").exc_info()
            payload = json.loads(JsonFormatter().format(exc_record))
        assert "ValueError" in payload["exception"]


class TestHumanReadableFormatter:
    def test_includes_level_and_message(self) -> None:
        output = HumanReadableFormatter().format(_record())
        assert "WARNING" in output
        assert "hello" in output

    def test_includes_correlation_suffix(self) -> None:
        with correlation_scope(request_id="req-1"):
            output = HumanReadableFormatter().format(_record())
        assert "request_id=req-1" in output

    def test_no_correlation_suffix_by_default(self) -> None:
        output = HumanReadableFormatter().format(_record())
        assert "request_id=" not in output
