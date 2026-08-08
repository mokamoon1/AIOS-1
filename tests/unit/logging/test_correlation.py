"""Correlation identifier tests (ADR-0010 section 5.4).

Verifies that Request ID, Event ID, and Trace ID propagate through
context scopes and are attached to emitted log records.
"""

from __future__ import annotations

import logging

import pytest

from aios.logging import CorrelationFilter, correlation_scope, current_correlation

pytestmark = pytest.mark.unit


class TestCurrentCorrelation:
    def test_default_correlation_is_empty(self) -> None:
        correlation = current_correlation()
        assert correlation.request_id is None
        assert correlation.event_id is None
        assert correlation.trace_id is None


class TestCorrelationScope:
    def test_scope_sets_identifiers(self) -> None:
        with correlation_scope(
            request_id="req-1", event_id="evt-1", trace_id="trace-1"
        ) as correlation:
            assert correlation.request_id == "req-1"
            assert current_correlation().request_id == "req-1"
            assert current_correlation().event_id == "evt-1"
            assert current_correlation().trace_id == "trace-1"

    def test_scope_restores_previous_values(self) -> None:
        with correlation_scope(request_id="outer"):
            with correlation_scope(request_id="inner"):
                assert current_correlation().request_id == "inner"
            assert current_correlation().request_id == "outer"
        assert current_correlation().request_id is None

    def test_nested_scope_partial_override(self) -> None:
        with (
            correlation_scope(event_id="evt-1"),
            correlation_scope(trace_id="trace-1"),
        ):
            assert current_correlation().event_id == "evt-1"
            assert current_correlation().trace_id == "trace-1"


class TestCorrelationFilter:
    def test_filter_attaches_identifiers(self) -> None:
        record = logging.LogRecord(
            name="aios.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        with correlation_scope(request_id="req-1", event_id="evt-1", trace_id="trace-1"):
            assert CorrelationFilter().filter(record) is True
        assert record.request_id == "req-1"
        assert record.event_id == "evt-1"
        assert record.trace_id == "trace-1"

    def test_filter_without_scope_sets_none(self) -> None:
        record = logging.LogRecord(
            name="aios.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        assert CorrelationFilter().filter(record) is True
        assert record.request_id is None
        assert record.event_id is None
        assert record.trace_id is None
