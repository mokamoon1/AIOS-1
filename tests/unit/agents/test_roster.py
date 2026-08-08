"""Tests for the concrete Phase 1 agent roster and CIO authority
(AIOS-401, AIOS-403, AIOS-604, ADR-0002)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from aios.agents.messages import AgentContext
from aios.agents.roster import (
    AGENT_CLASSES,
    CIOAgent,
    FundamentalAgent,
    MarketAgent,
    PortfolioAgent,
    RiskAgent,
    ShariahAgent,
    TechnicalAgent,
    create_agent,
    require_cio_authority,
)
from aios.agents.types import AgentType
from aios.data.models import PortfolioPosition, PositionStatus
from aios.errors import DataError, SecurityError
from aios.portfolio import PortfolioService


def test_roster_maps_all_seven_types() -> None:
    assert set(AGENT_CLASSES) == set(AgentType)
    assert len(AGENT_CLASSES) == 7


def test_create_agent_returns_correct_class() -> None:
    cases = {
        AgentType.CIO: CIOAgent,
        AgentType.SHARIAH: ShariahAgent,
        AgentType.MARKET: MarketAgent,
        AgentType.TECHNICAL: TechnicalAgent,
        AgentType.FUNDAMENTAL: FundamentalAgent,
        AgentType.RISK: RiskAgent,
        AgentType.PORTFOLIO: PortfolioAgent,
    }
    for agent_type, expected in cases.items():
        assert isinstance(create_agent(agent_type), expected)


def test_create_agent_unknown_type_raises() -> None:
    with pytest.raises(KeyError):
        create_agent("news")  # type: ignore[arg-type]


def test_each_agent_declares_metadata() -> None:
    for agent_type, cls in AGENT_CLASSES.items():
        instance = cls()
        assert instance.agent_type is agent_type
        assert instance.name
        assert instance.version
        assert instance.description


def test_only_cio_can_issue_final_recommendation() -> None:
    for agent_type, cls in AGENT_CLASSES.items():
        instance = cls()
        if agent_type is AgentType.CIO:
            assert instance.can_issue_final_recommendation is True
        else:
            assert instance.can_issue_final_recommendation is False


def test_cio_authority_enforced_for_non_cio() -> None:
    agent = MarketAgent()
    with pytest.raises(SecurityError):
        require_cio_authority(agent)


def test_cio_authority_allowed_for_cio() -> None:
    agent = CIOAgent()
    require_cio_authority(agent)


def _position(symbol: str, *, quantity: float, allocation: float, sector: str) -> PortfolioPosition:
    return PortfolioPosition(
        symbol=symbol,
        exchange="NASDAQ",
        quantity=quantity,
        entry_price=100.0,
        current_price=110.0,
        allocation=allocation,
        sector=sector,
        status=PositionStatus.OPEN,
    )


class _FakeReader:
    def __init__(self, positions: list[PortfolioPosition]) -> None:
        self._positions = positions

    def list_positions(
        self, *, status: PositionStatus | None = None
    ) -> Sequence[PortfolioPosition]:
        if status is None:
            return self._positions
        return [p for p in self._positions if p.status is status]


class _FailingReader:
    def list_positions(
        self, *, status: PositionStatus | None = None
    ) -> Sequence[PortfolioPosition]:
        raise DataError("storage unavailable")


def _context(request_id: str = "req-1") -> AgentContext:
    return AgentContext(request_id=request_id)


def test_create_agent_attaches_portfolio_service() -> None:
    service = PortfolioService(_FakeReader([]))
    agent = create_agent(AgentType.PORTFOLIO, portfolio_service=service)
    assert isinstance(agent, PortfolioAgent)
    assert agent.portfolio_service is service


def test_create_agent_rejects_portfolio_service_for_other_types() -> None:
    service = PortfolioService(_FakeReader([]))
    for agent_type in (
        AgentType.CIO,
        AgentType.SHARIAH,
        AgentType.MARKET,
        AgentType.TECHNICAL,
        AgentType.FUNDAMENTAL,
        AgentType.RISK,
    ):
        with pytest.raises(TypeError):
            create_agent(agent_type, portfolio_service=service)


async def test_portfolio_agent_without_service_uses_placeholder() -> None:
    agent = PortfolioAgent()
    agent.initialize()
    result = await agent.execute(_context())
    assert result.output["recommended_allocation"] is None
    assert result.output["rebalance_suggestion"] is None
    assert result.output["portfolio_impact"] == {}
    assert "Portfolio Service" in result.explanation


async def test_portfolio_agent_reports_snapshot() -> None:
    positions = [
        _position("AAPL", quantity=10.0, allocation=0.5, sector="Technology"),
        _position("JNJ", quantity=10.0, allocation=0.5, sector="Healthcare"),
    ]
    service = PortfolioService(_FakeReader(positions))
    agent = PortfolioAgent(portfolio_service=service)
    agent.initialize()
    result = await agent.execute(_context())
    impact = result.output["portfolio_impact"]
    assert impact["position_count"] == 2
    assert impact["sector_count"] == 2
    assert impact["total_value"] == pytest.approx(2200.0)
    assert impact["max_position_allocation"] == pytest.approx(0.5)
    assert result.output["recommended_allocation"] is None
    assert result.output["rebalance_suggestion"] is None
    assert result.confidence == 1.0


async def test_portfolio_agent_decorates_reader_failure() -> None:
    service = PortfolioService(_FailingReader())
    agent = PortfolioAgent(portfolio_service=service)
    agent.initialize()
    result = await agent.execute(_context())
    assert "error" in result.output["portfolio_impact"]
    assert result.confidence == 0.0
