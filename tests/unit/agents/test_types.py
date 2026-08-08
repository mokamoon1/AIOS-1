"""Tests for agent types, the Phase 1 core roster, and lifecycle states
(AIOS-401, AIOS-403, AIOS-604)."""

from __future__ import annotations

from aios.agents.types import AgentState, AgentType


def test_core_roster_has_exactly_seven_agents() -> None:
    expected = {
        AgentType.CIO,
        AgentType.SHARIAH,
        AgentType.MARKET,
        AgentType.TECHNICAL,
        AgentType.FUNDAMENTAL,
        AgentType.RISK,
        AgentType.PORTFOLIO,
    }
    assert set(AgentType) == expected


def test_technical_agent_is_independent() -> None:
    assert AgentType.TECHNICAL is not AgentType.MARKET


def test_no_news_agent_in_core_roster() -> None:
    assert {agent.value for agent in AgentType} == {
        "cio",
        "shariah",
        "market",
        "technical",
        "fundamental",
        "risk",
        "portfolio",
    }


def test_agent_state_lifecycle_values() -> None:
    assert AgentState.UNINITIALIZED.value == "uninitialized"
    assert AgentState.INITIALIZED.value == "initialized"
    assert AgentState.PROCESSING.value == "processing"
    assert AgentState.IDLE.value == "idle"
    assert AgentState.FAILED.value == "failed"
    assert AgentState.SHUTDOWN.value == "shutdown"
