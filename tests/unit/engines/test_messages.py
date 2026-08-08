"""Tests for standardized engine messages (AIOS-605 sections 11 and 12)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from aios.engines.messages import EngineInput, EngineOutput
from aios.engines.types import EngineType


def test_engine_input_requires_request_id() -> None:
    with pytest.raises(ValidationError):
        EngineInput(request_id="")


def test_engine_input_strips_request_id() -> None:
    engine_input = EngineInput(request_id="  req-1  ")
    assert engine_input.request_id == "req-1"


def test_engine_input_defaults() -> None:
    engine_input = EngineInput(request_id="req-1")
    assert engine_input.payload == {}
    assert engine_input.input_version == "1.0.0"


def test_engine_input_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EngineInput(request_id="req-1", unexpected="x")


def test_engine_output_carries_message_contract() -> None:
    output = EngineOutput(engine_type=EngineType.MARKET, engine_id="market-1", request_id="req-1")
    assert output.engine_type is EngineType.MARKET
    assert output.engine_id == "market-1"
    assert output.request_id == "req-1"
    assert output.output == {}
    assert output.explanation == ""
    assert output.confidence == 0.0
    assert output.input_version == "1.0.0"
    assert output.output_version == "1.0.0"
    assert output.processing_duration == 0.0
    assert isinstance(output.timestamp, datetime)


def test_engine_output_confidence_bounds() -> None:
    base = {"engine_type": EngineType.RISK, "engine_id": "risk-1", "request_id": "req-1"}
    with pytest.raises(ValidationError):
        EngineOutput(**base, confidence=1.5)
    with pytest.raises(ValidationError):
        EngineOutput(**base, confidence=-0.1)


def test_engine_output_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError):
        EngineOutput(
            engine_type=EngineType.TECHNICAL,
            engine_id="technical-1",
            request_id="req-1",
            processing_duration=-1.0,
        )


def test_engine_output_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EngineOutput(
            engine_type=EngineType.FUNDAMENTAL,
            engine_id="fundamental-1",
            request_id="req-1",
            extra="x",
        )


def test_engine_output_serializes_timestamp() -> None:
    output = EngineOutput(engine_type=EngineType.SIGNAL, engine_id="signal-1", request_id="req-1")
    dumped = output.model_dump(mode="json")
    assert "timestamp" in dumped
    assert "processing_duration" in dumped
    assert "input_version" in dumped
    assert "output_version" in dumped
    assert "confidence" in dumped
    assert "engine_id" in dumped
