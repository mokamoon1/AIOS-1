"""Concrete Phase 1 agent roster (AIOS-401, AIOS-403, AIOS-604).

The Phase 1 core agent roster is canonical in AIOS-604 and confirmed by
AIOS-401 and AIOS-403:

    1. CIO Agent
    2. Shariah Agent
    3. Market Agent
    4. Technical Agent
    5. Fundamental Agent
    6. Risk Agent
    7. Portfolio Agent

Broader agent lists in AIOS-101 and AIOS-102 (for example the News
Intelligence Agent) are future expansion, not part of the Phase 1 core
roster (AIOS-604 section 17).

This module also enforces the CIO authority rule from AIOS-403 section 14
and ADR-0002: only the CIO Agent may issue a final investment
recommendation; every other agent provides recommendations only.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from aios.agents.base import Agent
from aios.agents.messages import AgentContext, AgentResult
from aios.agents.types import AgentType
from aios.errors import SecurityError
from aios.events import EventBus
from aios.portfolio import PortfolioError, PortfolioService


def _scaffold_output(request_id: str) -> dict:
    """Build the placeholder output for a registered roster agent.

    Phase 1 concrete agents are registered and lifecycle-managed by the
    framework. Their specialized computation is performed by the
    corresponding engine (AIOS-605) and is wired in the Engine Framework
    step; this placeholder only acknowledges the request without fabricating
    any analysis result (AIOS-604 section 15).
    """
    return {"received": True, "request_id": request_id}


class CIOAgent(Agent):
    """Chief Intelligence Officer Agent (AIOS-604 section 7).

    Coordinates all agents, collects analytical outputs, resolves conflicts,
    evaluates confidence, and produces the final recommendation. The CIO
    Agent shall not bypass validation rules (AIOS-604 section 7, ADR-0002).
    """

    agent_type: ClassVar[AgentType] = AgentType.CIO
    name: ClassVar[str] = "CIO Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Coordinates all agents, resolves conflicts, evaluates confidence, "
        "and produces the final recommendation."
    )
    can_issue_final_recommendation: ClassVar[bool] = True

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=_scaffold_output(context.request_id),
            explanation=(
                "CIO agent registered. Final recommendation requires the "
                "Decision Engine output (wired in the Engine Framework step)."
            ),
            confidence=0.0,
        )


class ShariahAgent(Agent):
    """Shariah Compliance Agent (AIOS-604 section 8).

    Verifies compliance status, manages Shariah datasets, rejects prohibited
    securities, and tracks review history. All investment workflows begin
    with Shariah verification (AIOS-604 section 8).
    """

    agent_type: ClassVar[AgentType] = AgentType.SHARIAH
    name: ClassVar[str] = "Shariah Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Verifies compliance status, rejects prohibited securities, and tracks review history."
    )

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=_scaffold_output(context.request_id),
            explanation=(
                "Shariah agent registered. Compliance verification requires "
                "the Shariah data source (wired in a later step)."
            ),
            confidence=0.0,
        )


class MarketAgent(Agent):
    """Market Agent (AIOS-604 section 9).

    Analyzes overall market conditions, detects trends, evaluates
    volatility, and assesses market strength. Outputs are consumed by
    downstream agents (AIOS-604 section 9).
    """

    agent_type: ClassVar[AgentType] = AgentType.MARKET
    name: ClassVar[str] = "Market Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Analyzes overall market conditions, trends, volatility, and market strength."
    )

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=_scaffold_output(context.request_id),
            explanation=(
                "Market agent registered. Market analysis requires the "
                "Market Engine (AIOS-605, wired in a later step)."
            ),
            confidence=0.0,
        )


class TechnicalAgent(Agent):
    """Technical Analysis Agent (AIOS-604 section 10).

    Covers technical indicators, price action, market structure, Fibonacci
    analysis, Smart Money Concepts (SMC), and signal generation. Produces
    technical analysis results only (AIOS-604 section 10).
    """

    agent_type: ClassVar[AgentType] = AgentType.TECHNICAL
    name: ClassVar[str] = "Technical Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Technical indicators, price action, market structure, Fibonacci, "
        "SMC, and signal generation."
    )

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=_scaffold_output(context.request_id),
            explanation=(
                "Technical agent registered. Technical analysis requires the "
                "Technical Engine (AIOS-605, wired in a later step)."
            ),
            confidence=0.0,
        )


class FundamentalAgent(Agent):
    """Fundamental Analysis Agent (AIOS-604 section 11).

    Covers financial statement analysis, company valuation, profitability,
    growth assessment, and financial health. Produces standardized company
    evaluations (AIOS-604 section 11).
    """

    agent_type: ClassVar[AgentType] = AgentType.FUNDAMENTAL
    name: ClassVar[str] = "Fundamental Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Financial statement analysis, valuation, profitability, growth, and financial health."
    )

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=_scaffold_output(context.request_id),
            explanation=(
                "Fundamental agent registered. Fundamental analysis requires "
                "the Fundamental Engine (AIOS-605, wired in a later step)."
            ),
            confidence=0.0,
        )


class RiskAgent(Agent):
    """Risk Agent (AIOS-604 section 12).

    Covers position sizing, risk exposure, portfolio limits, stop-loss
    recommendations, and risk scoring. The Risk Agent may reject otherwise
    favorable opportunities (AIOS-604 section 12).
    """

    agent_type: ClassVar[AgentType] = AgentType.RISK
    name: ClassVar[str] = "Risk Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Position sizing, risk exposure, portfolio limits, stop-loss "
        "recommendations, and risk scoring."
    )

    async def _process(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=_scaffold_output(context.request_id),
            explanation=(
                "Risk agent registered. Risk evaluation requires the Risk "
                "Engine (AIOS-605, wired in a later step)."
            ),
            confidence=0.0,
        )


class PortfolioAgent(Agent):
    """Portfolio Agent (AIOS-604 section 13).

    Covers portfolio allocation, diversification, performance monitoring,
    and rebalancing recommendations. Maintains portfolio consistency
    (AIOS-604 section 13). Documented outputs: recommended allocation,
    portfolio impact, and rebalance suggestion (AIOS-403 section 10).
    """

    agent_type: ClassVar[AgentType] = AgentType.PORTFOLIO
    name: ClassVar[str] = "Portfolio Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Portfolio allocation, diversification, performance monitoring, "
        "and rebalancing recommendations."
    )

    def __init__(
        self,
        *,
        agent_id: str | None = None,
        bus: EventBus | None = None,
        logger: logging.Logger | None = None,
        portfolio_service: PortfolioService | None = None,
    ) -> None:
        super().__init__(agent_id=agent_id, bus=bus, logger=logger)
        self._portfolio_service = portfolio_service

    @property
    def portfolio_service(self) -> PortfolioService | None:
        """The Portfolio Service backing this agent (None until wired)."""
        return self._portfolio_service

    def attach_portfolio_service(self, service: PortfolioService) -> None:
        """Attach the Portfolio Service that supplies the current holdings view."""
        self._portfolio_service = service

    async def _process(self, context: AgentContext) -> AgentResult:
        output = {
            "recommended_allocation": None,
            "portfolio_impact": {},
            "rebalance_suggestion": None,
        }
        if self._portfolio_service is None:
            explanation = (
                "Portfolio agent requires the Portfolio Service (wired in "
                "the Portfolio Module step). Recommended allocation and "
                "rebalance suggestion are not fabricated because target "
                "allocation rules are not documented (AIOS-206 sections 6 "
                "and 9)."
            )
            return AgentResult(
                agent_type=self.agent_type,
                request_id=context.request_id,
                output=output,
                explanation=explanation,
                confidence=0.0,
            )
        try:
            snapshot = self._portfolio_service.current_snapshot()
        except PortfolioError as exc:
            output["portfolio_impact"] = {"error": str(exc)}
            return AgentResult(
                agent_type=self.agent_type,
                request_id=context.request_id,
                output=output,
                explanation=f"Portfolio impact unavailable: {exc}",
                confidence=0.0,
            )
        output["portfolio_impact"] = snapshot.model_dump(mode="json")
        explanation = (
            f"Portfolio agent reported the current holdings snapshot: "
            f"{snapshot.position_count} open position(s) across "
            f"{snapshot.sector_count} sector(s) with total market value "
            f"{snapshot.total_value:.2f} and weighted return "
            f"{snapshot.weighted_return_pct:.2f}%. Concentration values are "
            f"objective. Recommended allocation and rebalance suggestion are "
            f"not fabricated because target allocation rules are not "
            f"documented (AIOS-206 sections 6 and 9)."
        )
        confidence = 1.0 if snapshot.position_count > 0 else 0.5
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=output,
            explanation=explanation,
            confidence=confidence,
        )


AGENT_CLASSES: dict[AgentType, type[Agent]] = {
    AgentType.CIO: CIOAgent,
    AgentType.SHARIAH: ShariahAgent,
    AgentType.MARKET: MarketAgent,
    AgentType.TECHNICAL: TechnicalAgent,
    AgentType.FUNDAMENTAL: FundamentalAgent,
    AgentType.RISK: RiskAgent,
    AgentType.PORTFOLIO: PortfolioAgent,
}


def create_agent(
    agent_type: AgentType,
    *,
    agent_id: str | None = None,
    bus: EventBus | None = None,
    logger: logging.Logger | None = None,
    portfolio_service: PortfolioService | None = None,
) -> Agent:
    """Create an agent instance for a Phase 1 core roster type.

    ``portfolio_service`` is accepted only for the Portfolio Agent; passing
    it to another roster type raises :class:`TypeError`.

    Raises :class:`KeyError` for types outside the Phase 1 core roster.
    """
    if agent_type not in AGENT_CLASSES:
        raise KeyError(f"Agent type {agent_type!r} is not in the Phase 1 core roster")
    agent = AGENT_CLASSES[agent_type](agent_id=agent_id, bus=bus, logger=logger)
    if portfolio_service is not None:
        if not isinstance(agent, PortfolioAgent):
            raise TypeError(f"Agent type {agent_type.value!r} does not accept a portfolio service")
        agent.attach_portfolio_service(portfolio_service)
    return agent


def require_cio_authority(agent: Agent) -> None:
    """Enforce that only the CIO Agent may issue a final recommendation.

    Implements AIOS-403 section 14 and ADR-0002: only the CIO Agent produces
    final investment decisions; all other agents provide recommendations
    only.
    """
    if not agent.can_issue_final_recommendation or agent.agent_type is not AgentType.CIO:
        raise SecurityError("Only the CIO Agent may issue a final investment recommendation")
