"""Tests for the Agent Manager registry (AIOS-104 section 5.3)."""

from __future__ import annotations

import pytest

from aios.agents.exceptions import AgentNotFoundError, AgentRegistrationError
from aios.agents.manager import AgentManager
from aios.agents.messages import AgentContext
from aios.agents.roster import CIOAgent, MarketAgent, RiskAgent
from aios.agents.types import AgentState, AgentType


async def test_register_initializes_agent() -> None:
    manager = AgentManager()
    agent = MarketAgent()
    manager.register(agent)
    assert agent.state is AgentState.INITIALIZED
    assert manager.get(agent.agent_id) is agent


async def test_duplicate_registration_raises() -> None:
    manager = AgentManager()
    agent = MarketAgent()
    manager.register(agent)
    with pytest.raises(AgentRegistrationError):
        manager.register(agent)


async def test_register_already_initialized_agent_raises() -> None:
    manager = AgentManager()
    agent = MarketAgent()
    agent.initialize()
    with pytest.raises(AgentRegistrationError):
        manager.register(agent)


async def test_get_unknown_agent_raises() -> None:
    manager = AgentManager()
    with pytest.raises(AgentNotFoundError):
        manager.get("missing")


async def test_get_by_type() -> None:
    manager = AgentManager()
    market_a = MarketAgent()
    market_b = MarketAgent()
    cio = CIOAgent()
    manager.register(market_a)
    manager.register(market_b)
    manager.register(cio)
    assert manager.get_by_type(AgentType.MARKET) == [market_a, market_b]
    assert manager.get_by_type(AgentType.CIO) == [cio]


async def test_list_agents_preserves_registration_order() -> None:
    manager = AgentManager()
    market = MarketAgent()
    risk = RiskAgent()
    manager.register(market)
    manager.register(risk)
    assert manager.list_agents() == [market, risk]


async def test_status_reports_states() -> None:
    manager = AgentManager()
    market = MarketAgent()
    manager.register(market)
    assert manager.status() == {market.agent_id: AgentState.INITIALIZED}


async def test_unregister_shuts_down_and_removes() -> None:
    manager = AgentManager()
    agent = MarketAgent()
    manager.register(agent)
    manager.unregister(agent.agent_id)
    assert agent.state is AgentState.SHUTDOWN
    with pytest.raises(AgentNotFoundError):
        manager.get(agent.agent_id)


async def test_execute_routes_to_agent() -> None:
    manager = AgentManager()
    agent = MarketAgent()
    manager.register(agent)
    context = AgentContext(request_id="req-1", payload={"symbol": "AAPL"})
    result = await manager.execute(agent.agent_id, context)
    assert result.agent_type is AgentType.MARKET
    assert result.request_id == "req-1"


async def test_execute_by_type() -> None:
    manager = AgentManager()
    manager.register(MarketAgent())
    context = AgentContext(request_id="req-2")
    result = await manager.execute_by_type(AgentType.MARKET, context)
    assert result.agent_type is AgentType.MARKET


async def test_execute_by_type_unknown_raises() -> None:
    manager = AgentManager()
    context = AgentContext(request_id="req-3")
    with pytest.raises(AgentNotFoundError):
        await manager.execute_by_type(AgentType.TECHNICAL, context)
