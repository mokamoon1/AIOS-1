"""Tests for engine types and lifecycle states (AIOS-605 sections 3 and 4)."""

from __future__ import annotations

from aios.engines.types import EngineState, EngineType


def test_engine_type_roster_is_complete() -> None:
    assert {t.value for t in EngineType} == {
        "market",
        "technical",
        "fundamental",
        "risk",
        "decision",
        "signal",
    }


def test_engine_type_string_values() -> None:
    assert EngineType.MARKET.value == "market"
    assert EngineType.TECHNICAL.value == "technical"
    assert EngineType.FUNDAMENTAL.value == "fundamental"
    assert EngineType.RISK.value == "risk"
    assert EngineType.DECISION.value == "decision"
    assert EngineType.SIGNAL.value == "signal"


def test_engine_state_covers_lifecycle() -> None:
    assert {s.value for s in EngineState} == {
        "uninitialized",
        "initialized",
        "processing",
        "idle",
        "failed",
        "shutdown",
    }


def test_engine_state_order_of_members() -> None:
    members = list(EngineState)
    assert members.index(EngineState.UNINITIALIZED) < members.index(EngineState.INITIALIZED)
    assert members.index(EngineState.INITIALIZED) < members.index(EngineState.PROCESSING)
    assert members.index(EngineState.PROCESSING) < members.index(EngineState.IDLE)
    assert members.index(EngineState.IDLE) < members.index(EngineState.FAILED)
    assert members.index(EngineState.FAILED) < members.index(EngineState.SHUTDOWN)
