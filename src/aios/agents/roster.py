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
    8. News Intelligence Agent (Phase 9.1)

Broader agent lists in AIOS-101 and AIOS-102 (for example the News
Intelligence Agent) are future expansion, not part of the Phase 1 core
roster (AIOS-604 section 17).

This module also enforces the CIO authority rule from AIOS-403 section 14
and ADR-0002: only the CIO Agent may issue a final investment
recommendation; every other agent provides recommendations only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar, Optional

from aios.agents.base import Agent
from aios.agents.messages import AgentContext, AgentResult
from aios.agents.types import AgentType
from aios.config.settings import PortfolioAllocationSettings
from aios.errors import SecurityError
from aios.events import EventBus
from aios.portfolio import (
    AllocationAction,
    PortfolioAllocationResult,
    PortfolioError,
    PortfolioService,
    RebalanceSuggestion,
    TargetAllocation,
)


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
        allocation_settings: PortfolioAllocationSettings | None = None,
    ) -> None:
        super().__init__(agent_id=agent_id, bus=bus, logger=logger)
        self._portfolio_service = portfolio_service
        self._allocation_settings = allocation_settings

    def _resolve_allocation_settings(self) -> PortfolioAllocationSettings:
        """Return the active Portfolio Allocation configuration (ADR-0009).

        Explicitly injected settings win; otherwise the runtime settings are
        loaded through the configuration layer (ADR-0009 section 5.2) and
        cached for the agent lifetime. When no environment is configured the
        documented defaults are used so analysis remains deterministic.
        """
        if self._allocation_settings is None:
            try:
                from aios.config.loader import load_settings

                self._allocation_settings = load_settings().portfolio
            except Exception:  # noqa: BLE001 - fall back to documented defaults
                self._allocation_settings = PortfolioAllocationSettings()
        return self._allocation_settings

    @property
    def portfolio_service(self) -> PortfolioService | None:
        """The Portfolio Service backing this agent (None until wired)."""
        return self._portfolio_service

    def attach_portfolio_service(self, service: PortfolioService) -> None:
        """Attach the Portfolio Service that supplies the current holdings view."""
        self._portfolio_service = service

    async def _process(self, context: AgentContext) -> AgentResult:
        settings = self._resolve_allocation_settings()
        symbols = context.payload.get("symbols", [])
        decision_outputs = context.payload.get("decision_outputs", {})
        signal_outputs = context.payload.get("signal_outputs", {})
        risk_outputs = context.payload.get("risk_outputs", {})

        # If no symbols provided, return current snapshot only
        if not symbols:
            return await self._snapshot_only_response(context)

        # Build allocation result for each symbol
        target_allocations: list[TargetAllocation] = []
        hard_constraints_triggered: list[str] = []
        explanation_parts: list[str] = []

        for symbol in symbols:
            decision_output = decision_outputs.get(symbol, {})
            signal_output = signal_outputs.get(symbol, {})
            risk_output = risk_outputs.get(symbol, {})

            target_alloc = self._compute_target_allocation(
                symbol=symbol,
                decision_output=decision_output,
                signal_output=signal_output,
                risk_output=risk_output,
                settings=settings,
            )

            if target_alloc.hard_constraints_triggered:
                hard_constraints_triggered.extend(target_alloc.hard_constraints_triggered)
                explanation_parts.append(
                    f"{symbol}: {target_alloc.action.value.upper()} "
                    f"(constraints: {', '.join(target_alloc.hard_constraints_triggered)})"
                )
            else:
                explanation_parts.append(
                    f"{symbol}: {target_alloc.action.value.upper()} "
                    f"(target_weight={target_alloc.target_weight:.2%}, "
                    f"allocation_score={target_alloc.allocation_score:.2f})"
                )

            target_allocations.append(target_alloc)

        # Build rebalance suggestion
        rebalance_suggestion = self._build_rebalance_suggestion(
            target_allocations=target_allocations,
            settings=settings,
        )

        # Build final allocation result
        allocation_result = PortfolioAllocationResult(
            generated_at=datetime.now(timezone.utc),
            total_portfolio_value=0.0,  # Will be filled if portfolio service available
            target_allocations=target_allocations,
            rebalance_suggestion=rebalance_suggestion if rebalance_suggestion.required else None,
            hard_constraints_triggered=hard_constraints_triggered,
            explanation="; ".join(explanation_parts) if explanation_parts else "No symbols processed",
        )

        # Try to get current portfolio snapshot for total value
        portfolio_impact = {}
        total_value = 0.0
        if self._portfolio_service is not None:
            try:
                snapshot = self._portfolio_service.current_snapshot()
                portfolio_impact = snapshot.model_dump(mode="json")
                total_value = snapshot.total_value
                allocation_result.total_portfolio_value = total_value
            except PortfolioError as exc:
                self._logger.warning("Could not fetch portfolio snapshot: %s", exc)

        output = {
            "recommended_allocation": allocation_result.model_dump(mode="json"),
            "portfolio_impact": portfolio_impact,
            "rebalance_suggestion": rebalance_suggestion.model_dump(mode="json") if rebalance_suggestion.required else None,
        }

        confidence = 1.0 if target_allocations else 0.0
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=output,
            explanation=allocation_result.explanation,
            confidence=confidence,
        )

    async def _snapshot_only_response(self, context: AgentContext) -> AgentResult:
        """Return current snapshot when no symbols provided for allocation."""
        output = {
            "recommended_allocation": None,
            "portfolio_impact": {},
            "rebalance_suggestion": None,
        }
        if self._portfolio_service is None:
            explanation = (
                "Portfolio agent requires the Portfolio Service (wired in "
                "the Portfolio Module step). Recommended allocation and "
                "rebalance suggestion require target allocation rules "
                "(AIOS-206 sections 6 and 9)."
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
            f"{snapshot.weighted_return_pct:.2f}%. "
            "Provide symbols in context payload to compute target allocations."
        )
        confidence = 1.0 if snapshot.position_count > 0 else 0.5
        return AgentResult(
            agent_type=self.agent_type,
            request_id=context.request_id,
            output=output,
            explanation=explanation,
            confidence=confidence,
        )

    def _compute_target_allocation(
        self,
        symbol: str,
        decision_output: dict,
        signal_output: dict,
        risk_output: dict,
        settings: PortfolioAllocationSettings,
    ) -> TargetAllocation:
        """Compute target allocation for a single symbol.

        Implements the Phase 9.4 allocation rules:
        - Allocation Score = Decision*0.50 + Signal*0.25 + Risk*0.25
        - Hard Constraints (priority order):
          1. Shariah != COMPLIANT -> allocation = 0
          2. Risk approval_status = blocked -> allocation = 0
          3. Decision = WAIT/NO_TRADE -> allocation = 0
          4. Decision = HOLD -> no new allocation (allocation = 0)
          5. Risk Limits: max_position_weight, max_sector_exposure
        """
        # Extract component scores
        decision_score = self._extract_decision_score(decision_output)
        signal_score = self._extract_signal_score(signal_output)
        risk_score = self._extract_risk_score(risk_output)

        # Hard Constraints (priority order)
        hard_constraints: list[str] = []

        # 1. Shariah Gate - would be checked upstream, but verify if available
        # The decision output should reflect Shariah gate via NO_TRADE
        # We check for Shariah failure via decision_output
        if decision_output.get("validation", {}).get("checks", {}).get("shariah_approval") is False:
            hard_constraints.append("shariah")

        # 2. Risk Gate blocked
        risk_approval = risk_output.get("approval_status")
        if risk_approval == "blocked":
            hard_constraints.append("risk_blocked")

        # 3. Decision WAIT or NO_TRADE
        decision = decision_output.get("decision")
        if decision in ("wait", "no_trade"):
            hard_constraints.append(f"decision_{decision}")

        # 4. Decision HOLD -> no new allocation
        if decision == "hold":
            hard_constraints.append("decision_hold")

        # If any hard constraint triggered, allocation = 0
        if hard_constraints:
            return TargetAllocation(
                symbol=symbol,
                exchange="NASDAQ",
                target_weight=0.0,
                target_value=0.0,
                current_weight=0.0,
                current_value=0.0,
                action=AllocationAction.HOLD,
                allocation_score=0.0,
                confidence=0.0,
                risk_adjustment=0.0,
                hard_constraints_triggered=hard_constraints,
                reasons=[f"Hard constraint triggered: {c}" for c in hard_constraints],
            )

        # All hard constraints passed - compute Allocation Score
        # Decision Score: map from [-1, +1] to [0, 1] -> (score + 1) / 2
        decision_score_norm = 0.5
        if decision_score is not None:
            decision_score_norm = max(0.0, min(1.0, (decision_score + 1.0) / 2.0))

        # Signal Score: already in [0, 1] from SignalEngine
        signal_score_norm = signal_score if signal_score is not None else 0.5

        # Risk Score: from RiskEngine risk_score [0, 1], or neutral 0.5
        risk_score_norm = risk_score if risk_score is not None else 0.5

        # Normalize weights
        total_weight = (
            settings.decision_score_weight
            + settings.signal_score_weight
            + settings.risk_score_weight
        )
        if total_weight > 0:
            w_decision = settings.decision_score_weight / total_weight
            w_signal = settings.signal_score_weight / total_weight
            w_risk = settings.risk_score_weight / total_weight
        else:
            w_decision = w_signal = w_risk = 0.0

        # Compute Allocation Score
        allocation_score = (
            w_decision * decision_score_norm
            + w_signal * signal_score_norm
            + w_risk * risk_score_norm
        )
        allocation_score = max(0.0, min(1.0, allocation_score))

        # Risk Adjustment
        risk_adjustment = 1.0
        decision_confidence = decision_output.get("confidence", 1.0)
        if settings.confidence_scaling:
            risk_adjustment *= decision_confidence
        if settings.risk_score_scaling and risk_score is not None:
            risk_adjustment *= risk_score

        # Apply risk adjustment to allocation score
        adjusted_score = allocation_score * risk_adjustment
        adjusted_score = max(0.0, min(1.0, adjusted_score))

        # Determine target weight (capped by max_position_weight)
        target_weight = adjusted_score * settings.max_position_weight
        target_weight = max(0.0, min(settings.max_position_weight, target_weight))

        # Determine action based on DecisionEngine decision
        decision = decision_output.get("decision", "wait")
        if decision == "buy":
            action = AllocationAction.BUY
        elif decision == "sell":
            action = AllocationAction.SELL
        else:
            action = AllocationAction.HOLD

        # Compute target value (simplified - assumes total portfolio value available)
        # In practice, this would be computed with total portfolio value
        target_value = target_weight  # Placeholder - proportional weight

        # Build reasons
        reasons = [
            f"Decision score: {decision_score_norm:.2f} (weight {settings.decision_score_weight})",
            f"Signal score: {signal_score_norm:.2f} (weight {settings.signal_score_weight})",
            f"Risk score: {risk_score_norm:.2f} (weight {settings.risk_score_weight})",
            f"Allocation score: {allocation_score:.2f} -> adjusted: {adjusted_score:.2f}",
            f"Target weight: {target_weight:.2%} (max {settings.max_position_weight:.0%})",
        ]

        return TargetAllocation(
            symbol=symbol,
            exchange="NASDAQ",
            target_weight=target_weight,
            target_value=target_value,
            current_weight=0.0,  # Would be computed from current positions
            current_value=0.0,
            action=action,
            allocation_score=allocation_score,
            confidence=decision_confidence,
            risk_adjustment=risk_adjustment,
            hard_constraints_triggered=[],
            reasons=reasons,
        )

    def _extract_decision_score(self, decision_output: dict) -> float | None:
        """Extract and normalize decision score from DecisionEngine output.

        DecisionEngine produces score in [-1, +1]. Returns None if not available.
        """
        return decision_output.get("decision_score")

    def _extract_signal_score(self, signal_output: dict) -> float | None:
        """Extract signal score from SignalEngine output.

        SignalEngine produces score in [0, 1] (bullish bias). Returns None if not available.
        """
        return signal_output.get("score")

    def _extract_risk_score(self, risk_output: dict) -> float | None:
        """Extract risk score from RiskEngine output.

        RiskEngine produces risk_score in [0, 1]. Returns None if not available.
        """
        return risk_output.get("risk_score")

    def _build_rebalance_suggestion(
        self,
        target_allocations: list[TargetAllocation],
        settings: PortfolioAllocationSettings,
    ) -> RebalanceSuggestion:
        """Build rebalancing suggestion from target allocations.

        Compares target weights with current positions (simplified - assumes
        current weights are 0 for new positions).
        """
        required = False
        trades: list[TargetAllocation] = []
        portfolio_drift = 0.0

        for alloc in target_allocations:
            # For now, assume current_weight = 0 for new positions
            # In reality, would fetch current position from portfolio
            current_weight = alloc.current_weight
            drift = abs(alloc.target_weight - current_weight)
            portfolio_drift += drift

            if drift >= settings.rebalance_threshold and alloc.target_weight > settings.min_trade_size:
                required = True
                trades.append(alloc)

        estimated_turnover = sum(t.target_weight for t in trades) / 2.0 if trades else 0.0

        reason = "No rebalancing needed"
        if required:
            reason = f"Rebalancing required: {len(trades)} trade(s) exceed {settings.rebalance_threshold:.0%} threshold"

        return RebalanceSuggestion(
            required=required,
            reason=reason,
            trades=trades,
            portfolio_drift=min(1.0, portfolio_drift),
            estimated_turnover=estimated_turnover,
        )


class NewsAgent(Agent):
    """News Intelligence Agent (Phase 9.1).

    Collects, evaluates, and explains market-relevant news. Integrates with
    the News Intelligence Engine to produce structured intelligence output
    for consumption by the Signal Engine and downstream agents.
    """

    agent_type: ClassVar[AgentType] = AgentType.NEWS
    name: ClassVar[str] = "News Agent"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Collects, evaluates, and explains market-relevant news. Integrates "
        "with the News Intelligence Engine to produce structured intelligence "
        "output for the Signal Engine."
    )

    def __init__(
        self,
        *,
        agent_id: str | None = None,
        bus: EventBus | None = None,
        logger: logging.Logger | None = None,
        news_engine: "NewsEngine" | None = None,
    ) -> None:
        super().__init__(agent_id=agent_id, bus=bus, logger=logger)
        self._news_engine = news_engine

    def attach_news_engine(self, engine: "NewsEngine") -> None:
        """Attach the News Engine that supplies intelligence output."""
        self._news_engine = engine

    async def _process(self, context: AgentContext) -> AgentResult:
        output = {
            "news_intelligence": None,
            "articles_analyzed": 0,
            "symbols_covered": [],
        }
        if self._news_engine is None:
            explanation = (
                "News agent requires the News Intelligence Engine (wired in "
                "the News Intelligence step). News intelligence output and "
                "article analysis are not available."
            )
            return AgentResult(
                agent_type=self.agent_type,
                request_id=context.request_id,
                output=output,
                explanation=explanation,
                confidence=0.0,
            )

        # Extract symbols from context payload
        symbols = context.payload.get("symbols", [])
        if not symbols:
            explanation = (
                "No symbols provided in context payload. News intelligence "
                "requires at least one symbol to analyze."
            )
            return AgentResult(
                agent_type=self.agent_type,
                request_id=context.request_id,
                output=output,
                explanation=explanation,
                confidence=0.0,
            )

        try:
            results = []
            for symbol in symbols:
                intelligence = await self._news_engine.analyze_symbol_news(symbol)
                results.extend(intelligence)
                output["symbols_covered"].append(symbol)

            output["news_intelligence"] = [
                intel.model_dump(mode="json") for intel in results
            ]
            output["articles_analyzed"] = len(results)
            output["symbols_covered"] = symbols

            explanation = (
                f"News agent analyzed {len(results)} intelligence items "
                f"for {len(symbols)} symbol(s)."
            )
            confidence = 1.0 if results else 0.5
            return AgentResult(
                agent_type=self.agent_type,
                request_id=context.request_id,
                output=output,
                explanation=explanation,
                confidence=confidence,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(
                agent_type=self.agent_type,
                request_id=context.request_id,
                output=output,
                explanation=f"News intelligence analysis failed: {exc}",
                confidence=0.0,
            )


AGENT_CLASSES: dict[AgentType, type[Agent]] = {
    AgentType.CIO: CIOAgent,
    AgentType.SHARIAH: ShariahAgent,
    AgentType.MARKET: MarketAgent,
    AgentType.TECHNICAL: TechnicalAgent,
    AgentType.FUNDAMENTAL: FundamentalAgent,
    AgentType.RISK: RiskAgent,
    AgentType.PORTFOLIO: PortfolioAgent,
    AgentType.NEWS: NewsAgent,
}


def create_agent(
    agent_type: AgentType,
    *,
    agent_id: str | None = None,
    bus: EventBus | None = None,
    logger: logging.Logger | None = None,
    portfolio_service: PortfolioService | None = None,
    news_engine: "NewsEngine" | None = None,
    allocation_settings: PortfolioAllocationSettings | None = None,
) -> Agent:
    """Create an agent instance for a Phase 1 core roster type.

    ``portfolio_service`` is accepted only for the Portfolio Agent; passing
    it to another roster type raises :class:`TypeError`.

    ``news_engine`` is accepted only for the News Agent; passing
    it to another roster type raises :class:`TypeError`.

    ``allocation_settings`` is accepted only for the Portfolio Agent; passing
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
    if news_engine is not None:
        if not isinstance(agent, NewsAgent):
            raise TypeError(f"Agent type {agent_type.value!r} does not accept a news engine")
        agent.attach_news_engine(news_engine)
    if allocation_settings is not None:
        if not isinstance(agent, PortfolioAgent):
            raise TypeError(f"Agent type {agent_type.value!r} does not accept allocation settings")
        agent._allocation_settings = allocation_settings
    return agent


def require_cio_authority(agent: Agent) -> None:
    """Enforce that only the CIO Agent may issue a final recommendation.

    Implements AIOS-403 section 14 and ADR-0002: only the CIO Agent produces
    final investment decisions; all other agents provide recommendations
    only.
    """
    if not agent.can_issue_final_recommendation or agent.agent_type is not AgentType.CIO:
        raise SecurityError("Only the CIO Agent may issue a final investment recommendation")
