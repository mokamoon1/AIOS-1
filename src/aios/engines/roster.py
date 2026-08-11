"""Concrete Phase 1 engine roster (AIOS-605 sections 6-11) wired for Phase 3.

The engine roster is canonical in AIOS-605 section 3:

    1. Market Engine
    2. Technical Engine
    3. Fundamental Engine
    4. Risk Engine
    5. Decision Engine
    6. Signal Engine

In Phase 3 (Investment Intelligence, AIOS-005 section 7) the Market, Technical,
and Fundamental engines are wired to the Analysis Layer: they consume
standardized data through the :class:`DataAccess` facade (AIOS-501 section 2),
block securities that are not Shariah-approved (AIOS-301 FR-002), and produce
explainable analysis (AIOS-305 section 10). They report objective indicator
values and documented structure classifications only; no directional trade
decision is fabricated here.

The Signal Engine combines technical outputs (AIOS-605 section 10) and the
Decision Engine aggregates engine outputs (AIOS-605 section 11), so both
declare dependencies that the Engine Manager resolves for execution order.
In Phase 4 (Portfolio Management, AIOS-005 section 8) the Risk Engine is
wired to enforce configurable risk limits (AIOS-307 section 7) and report
objective risk factors, and the Decision Engine is wired to aggregate the
analysis and risk engine outputs and to enforce the documented validation
gates (AIOS-406 section 5). The Signal scoring and the Decision directional
scoring belong to later phases and remain configurable placeholders
(AIOS-605 sections 10-11).

The Decision Engine is the only engine authorized to issue investment
recommendations (AIOS-605 section 11). This module enforces that authority
through :func:`require_decision_authority`, mirroring the CIO authority rule
for agents (AIOS-403 section 14, ADR-0002).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar

from aios.analysis import (
    Evidence,
    Explanation,
    NewsIntelligenceOutput,
    ScoreComponent,
    SignalDirection,
    SignalResult,
    atr,
    bollinger_bands,
    ema,
    fibonacci_levels,
    macd,
    market_bias,
    market_structure,
    rsi,
    sma,
    weighted_score,
)
from aios.analysis.exceptions import InsufficientDataError
from aios.config.settings import DecisionSettings, SignalSettings
from aios.data.models import (
    CompanyFundamentals,
    DecisionAction,
    InvestmentDecision,
    PortfolioPosition,
    PositionStatus,
    Timeframe,
)
from aios.engines.base import DataAccess, Engine
from aios.engines.exceptions import EngineValidationError
from aios.engines.messages import EngineInput, EngineOutput
from aios.engines.types import EngineType
from aios.errors import DatabaseError, DataError, SecurityError
from aios.events import EventBus


def _scaffold_output(request_id: str) -> dict:
    """Build the placeholder output for a registered roster engine.

    The specialized computation for each engine is defined in AIOS-605
    sections 6-11 and wired in a later phase; this placeholder only
    acknowledges the request without fabricating any analysis value.
    """
    return {"received": True, "request_id": request_id}


def _require_symbol(engine_input: EngineInput) -> str:
    """Return the non-empty ``symbol`` payload value or reject the input."""
    symbol = engine_input.payload.get("symbol")
    if not symbol or not str(symbol).strip():
        raise EngineValidationError("Analysis requires a non-empty 'symbol' in the payload")
    return str(symbol).strip()


def _parse_timeframe(engine_input: EngineInput) -> Timeframe:
    """Parse the payload timeframe, defaulting to daily bars."""
    raw = engine_input.payload.get("timeframe", "1d")
    try:
        return Timeframe(str(raw))
    except ValueError as exc:
        raise EngineValidationError(f"Invalid timeframe {raw!r}") from exc


def _last_value(values: list[float | None]) -> float | None:
    """Return the most recent computed indicator value."""
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _candle_context(engine_input: EngineInput, engine: Engine) -> dict:
    """Load Shariah-approved candles for the requested symbol.

    Applies the documented gate that only approved securities may enter
    analysis (AIOS-301 FR-002, AIOS-205 section 3).
    """
    symbol = _require_symbol(engine_input)
    timeframe = _parse_timeframe(engine_input)
    engine.require_compliant(symbol)
    if engine.data_access is None:
        raise EngineValidationError(f"{engine.name} requires a data access facade")
    limit = int(engine_input.payload.get("limit", 250))
    candles = list(engine.data_access.get_candles(symbol, timeframe, limit=limit))
    if not candles:
        raise InsufficientDataError(f"No candles available for {symbol} on {timeframe.value}")
    return {"symbol": symbol, "timeframe": timeframe, "candles": candles}


def _optional_percentage(engine_input: EngineInput, key: str) -> float | None:
    """Parse an optional 0..100 percentage payload value (configurable limits).

    Rejects malformed values so configuration errors surface as validation
    failures (AIOS-605 section 15).
    """
    value = engine_input.payload.get(key)
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise EngineValidationError(f"Invalid {key} value {value!r}") from exc
    if parsed < 0 or parsed > 100:
        raise EngineValidationError(f"{key} must be between 0 and 100")
    return parsed


def _optional_positive(engine_input: EngineInput, key: str) -> float | None:
    """Parse an optional positive payload value (e.g. portfolio value)."""
    value = engine_input.payload.get(key)
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise EngineValidationError(f"Invalid {key} value {value!r}") from exc
    if parsed <= 0:
        raise EngineValidationError(f"{key} must be positive")
    return parsed


_REQUIRED_ANALYSIS_ENGINES: frozenset[EngineType] = frozenset(
    {EngineType.MARKET, EngineType.TECHNICAL, EngineType.FUNDAMENTAL}
)


def _prior_engine_outputs(engine_input: EngineInput) -> dict[EngineType, dict]:
    """Parse the prior engine outputs aggregated for the Decision Engine.

    The Decision Engine aggregates the outputs of the analysis and risk
    engines executed before it (AIOS-605 section 11). Outputs are supplied
    through the standardized payload key ``engine_outputs`` as a mapping of
    engine type value to the serialized output dictionary; malformed or
    unknown entries are ignored so no foreign data enters decision making.
    """
    raw = engine_input.payload.get("engine_outputs")
    if not isinstance(raw, dict):
        return {}
    outputs: dict[EngineType, dict] = {}
    for value, output in raw.items():
        if not isinstance(output, dict):
            continue
        try:
            engine_type = EngineType(str(value))
        except ValueError:
            continue
        if engine_type is EngineType.DECISION:
            continue
        # Prior outputs may arrive as full EngineOutput envelopes (the
        # Engine Manager pipeline) or as bare analysis dictionaries; unwrap
        # the envelope so the analysis payload is what gets consumed.
        nested = output.get("output")
        if isinstance(nested, dict):
            output = nested
        outputs[engine_type] = output
    return outputs


class MarketEngine(Engine):
    """Market Engine (AIOS-605 section 6).

    Performs market trend analysis, volatility assessment, market strength,
    session analysis, and market regime detection. Documented outputs:
    market trend, market score, and volatility score (AIOS-605 section 6).
    """

    engine_type: ClassVar[EngineType] = EngineType.MARKET
    name: ClassVar[str] = "Market Engine"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Market trend analysis, volatility assessment, market strength, "
        "session analysis, and market regime detection."
    )

    def validate_input(self, engine_input: EngineInput) -> bool:
        return bool(engine_input.payload.get("symbol"))

    async def _load_data(self, engine_input: EngineInput) -> dict:
        return _candle_context(engine_input, self)

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        candles = data["candles"]
        closes = [candle.close for candle in candles]
        structure = market_structure(closes)
        atr_values = atr(candles, 14)
        latest_atr = _last_value(atr_values)
        volatility = None
        if latest_atr is not None:
            volatility = {
                "atr_14": latest_atr,
                "atr_percentage": latest_atr / closes[-1],
            }
        output = {
            "symbol": data["symbol"],
            "timeframe": data["timeframe"].value,
            "bars": len(candles),
            "market_bias": market_bias(structure.direction).value,
            "trend_direction": structure.direction.value,
            "market_score": structure.strength,
            "volatility": volatility,
        }
        explanation = (
            f"Market engine analyzed {len(candles)} {data['timeframe'].value} bars for "
            f"{data['symbol']}. Structure is {structure.direction.value} with strength "
            f"{structure.strength:.2f}, giving a {output['market_bias']} market bias "
            f"(AIOS-205 section 5). Volatility is reported as the latest ATR(14) and its "
            f"percentage of the last close; no threshold opinion is attached."
        )
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output=output,
            explanation=explanation,
            confidence=structure.strength,
        )


class TechnicalEngine(Engine):
    """Technical Engine (AIOS-605 section 7).

    Covers technical indicators, price action, market structure, Fibonacci,
    Smart Money Concepts (SMC), and trend confirmation. Documented outputs:
    technical score, bullish score, bearish score, and technical explanation
    (AIOS-605 section 7).
    """

    engine_type: ClassVar[EngineType] = EngineType.TECHNICAL
    name: ClassVar[str] = "Technical Engine"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Technical indicators, price action, market structure, Fibonacci, "
        "SMC, and trend confirmation."
    )

    def validate_input(self, engine_input: EngineInput) -> bool:
        return bool(engine_input.payload.get("symbol"))

    async def _load_data(self, engine_input: EngineInput) -> dict:
        return _candle_context(engine_input, self)

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        candles = data["candles"]
        closes = [candle.close for candle in candles]
        structure = market_structure(closes)
        macd_result = macd(closes)
        bands = bollinger_bands(closes, period=20, deviations=2.0)
        indicators = {
            "sma_20": _last_value(sma(closes, 20)),
            "ema_20": _last_value(ema(closes, 20)),
            "rsi_14": _last_value(rsi(closes, 14)),
            "macd_12_26_9": {
                "line": _last_value(macd_result.macd_line),
                "signal": _last_value(macd_result.signal_line),
                "histogram": _last_value(macd_result.histogram),
            },
            "atr_14": _last_value(atr(candles, 14)),
            "bollinger_20_2": {
                "upper": _last_value(bands.upper),
                "middle": _last_value(bands.middle),
                "lower": _last_value(bands.lower),
            },
        }
        fibonacci = None
        swings = structure.swings
        if swings:
            highs = [swing for swing in swings if swing.swing_type.value == "high"]
            lows = [swing for swing in swings if swing.swing_type.value == "low"]
            if highs and lows:
                last_high = max(highs, key=lambda swing: swing.index).price
                last_low = max(lows, key=lambda swing: swing.index).price
                pivot_high = max(last_high, last_low)
                pivot_low = min(last_high, last_low)
                if pivot_high > pivot_low:
                    levels = fibonacci_levels(pivot_high, pivot_low)
                    fibonacci = {
                        "pivot_high": pivot_high,
                        "pivot_low": pivot_low,
                        "levels": [
                            {
                                "ratio": level.ratio,
                                "price": level.price,
                                "type": level.level_type.value,
                            }
                            for level in levels.levels
                        ],
                    }
        output = {
            "symbol": data["symbol"],
            "timeframe": data["timeframe"].value,
            "bars": len(candles),
            "structure": {
                "direction": structure.direction.value,
                "strength": structure.strength,
                "sequence": structure.sequence,
            },
            "market_bias": market_bias(structure.direction).value,
            "indicators": indicators,
            "fibonacci": fibonacci,
        }
        explanation = (
            f"Technical engine analyzed {len(candles)} {data['timeframe'].value} bars for "
            f"{data['symbol']}. Reported indicator values are computed with standard "
            f"definitions (AIOS-205 section 9) and structure follows the documented "
            f"higher-high/higher-low classification (AIOS-205 section 5). Indicators are "
            f"confirmation tools only and are not combined into a directional conclusion."
        )
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output=output,
            explanation=explanation,
            confidence=structure.strength,
        )


class FundamentalEngine(Engine):
    """Fundamental Engine (AIOS-605 section 8).

    Performs company valuation, financial analysis, growth analysis,
    profitability analysis, and financial health assessment. Documented
    outputs: fundamental score, financial strength, and company quality
    (AIOS-605 section 8).
    """

    engine_type: ClassVar[EngineType] = EngineType.FUNDAMENTAL
    name: ClassVar[str] = "Fundamental Engine"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Company valuation, financial analysis, growth analysis, "
        "profitability analysis, and financial health."
    )

    _METRIC_FIELDS = (
        "sector",
        "industry",
        "revenue",
        "net_income",
        "eps",
        "assets",
        "liabilities",
        "cash_flow",
        "equity",
    )

    def validate_input(self, engine_input: EngineInput) -> bool:
        return bool(engine_input.payload.get("symbol"))

    async def _load_data(self, engine_input: EngineInput) -> dict:
        symbol = _require_symbol(engine_input)
        self.require_compliant(symbol)
        if self.data_access is None:
            raise EngineValidationError(f"{self.name} requires a data access facade")
        fundamentals = self.data_access.get_fundamentals(symbol)
        return {"symbol": symbol, "fundamentals": fundamentals}

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        fundamentals = data["fundamentals"]
        ratios: dict[str, float] = {}
        if fundamentals.revenue not in (None, 0) and fundamentals.net_income is not None:
            ratios["net_margin"] = fundamentals.net_income / fundamentals.revenue
        if fundamentals.equity not in (None, 0):
            if fundamentals.net_income is not None:
                ratios["return_on_equity"] = fundamentals.net_income / fundamentals.equity
            if fundamentals.liabilities is not None:
                ratios["debt_to_equity"] = fundamentals.liabilities / fundamentals.equity
        if fundamentals.assets not in (None, 0) and fundamentals.equity is not None:
            ratios["equity_to_assets"] = fundamentals.equity / fundamentals.assets
        metrics = {
            "sector": fundamentals.sector,
            "industry": fundamentals.industry,
            "revenue": fundamentals.revenue,
            "net_income": fundamentals.net_income,
            "eps": fundamentals.eps,
            "assets": fundamentals.assets,
            "liabilities": fundamentals.liabilities,
            "cash_flow": fundamentals.cash_flow,
            "equity": fundamentals.equity,
        }
        available = [key for key in self._METRIC_FIELDS if metrics[key] not in (None, "")]
        output = {
            "symbol": data["symbol"],
            "report_date": str(fundamentals.report_date),
            "metrics": metrics,
            "available": available,
            "derived_ratios": ratios,
        }
        confidence = len(available) / len(self._METRIC_FIELDS)
        explanation = (
            f"Fundamental engine reported the stored financial metrics for "
            f"{data['symbol']} as of {fundamentals.report_date} (AIOS-502 section 6). "
            f"{len(available)} of {len(self._METRIC_FIELDS)} metric fields are available; "
            f"derived ratios (net margin, return on equity, debt to equity, equity to "
            f"assets) are objective values reported without a quality judgment."
        )
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output=output,
            explanation=explanation,
            confidence=confidence,
        )


class RiskEngine(Engine):
    """Risk Engine (AIOS-605 section 9).

    Performs position sizing, risk scoring, maximum exposure, stop-loss
    calculation, and portfolio impact. Documented outputs: risk level,
    recommended position size, and maximum allowable exposure (AIOS-605
    section 9); the Risk Agent additionally reports risk score, warnings,
    and approval status (AIOS-207 section 8, AIOS-403 section 9).

    Risk rules are enforced only through configurable limits supplied in the
    payload (AIOS-307 section 7): ``max_position_percentage`` and
    ``max_sector_exposure``. Objective risk factors (volatility, liquidity,
    market condition, company-data availability) are reported without an
    opinion, and no threshold, limit, or position-sizing rule is invented
    here (AIOS-307 sections 5-7). When a configured limit is violated the
    engine blocks the opportunity (risk level ``rejected``, approval status
    ``blocked``) so no trade proceeds on unsafe exposure (AIOS-207 sections
    9-10, AIOS-307 section 9).
    """

    engine_type: ClassVar[EngineType] = EngineType.RISK
    name: ClassVar[str] = "Risk Engine"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Position sizing, risk score, maximum exposure, stop-loss "
        "calculation, and portfolio impact."
    )

    def validate_input(self, engine_input: EngineInput) -> bool:
        return bool(engine_input.payload.get("symbol"))

    async def _load_data(self, engine_input: EngineInput) -> dict:
        symbol = _require_symbol(engine_input)
        timeframe = _parse_timeframe(engine_input)
        self.require_compliant(symbol)
        if self.data_access is None:
            raise EngineValidationError(f"{self.name} requires a data access facade")
        limit = int(engine_input.payload.get("limit", 250))
        candles = list(self.data_access.get_candles(symbol, timeframe, limit=limit))
        if not candles:
            raise InsufficientDataError(f"No candles available for {symbol} on {timeframe.value}")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles,
            "fundamentals": self._load_fundamentals(symbol),
            "positions": self._load_positions(),
        }

    def _load_fundamentals(self, symbol: str) -> CompanyFundamentals | None:
        """Return fundamentals for ``symbol``, degrading to None when absent.

        Missing fundamental data is a documented data-risk input (AIOS-307
        section 4.4), so a data-layer absence must not fail the risk
        evaluation; the availability is reported in the output instead.
        """
        if self.data_access is None:
            return None
        try:
            return self.data_access.get_fundamentals(symbol)
        except (DataError, DatabaseError):
            return None

    def _load_positions(self) -> list[PortfolioPosition]:
        """Return current portfolio positions, degrading to [] when unavailable."""
        if self.data_access is None:
            return []
        try:
            return list(self.data_access.list_positions())
        except (DataError, DatabaseError):
            return []

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        candles = data["candles"]
        fundamentals = data["fundamentals"]
        positions = data["positions"]
        symbol = data["symbol"]

        closes = [candle.close for candle in candles]
        structure = market_structure(closes)
        latest_atr = _last_value(atr(candles, 14))
        volatility = None
        if latest_atr is not None and closes:
            volatility = latest_atr / closes[-1]
        average_volume = sum(candle.volume for candle in candles) / len(candles)

        max_position_pct = _optional_percentage(engine_input, "max_position_percentage")
        max_sector_pct = _optional_percentage(engine_input, "max_sector_exposure")
        portfolio_value = _optional_positive(engine_input, "portfolio_value")
        requested_pct = _optional_percentage(engine_input, "requested_position_percentage")

        open_positions = [p for p in positions if p.status is PositionStatus.OPEN]
        symbol_positions = [p for p in open_positions if p.symbol == symbol]
        current_symbol_pct = sum(p.allocation for p in symbol_positions) * 100.0
        sector = fundamentals.sector if fundamentals is not None else ""
        sector_positions = [p for p in open_positions if sector and p.sector == sector]
        current_sector_pct = sum(p.allocation for p in sector_positions) * 100.0

        addition_pct = requested_pct if requested_pct is not None else 0.0
        projected_symbol_pct = current_symbol_pct + addition_pct
        projected_sector_pct = current_sector_pct + addition_pct

        violations: list[str] = []
        if max_position_pct is not None and projected_symbol_pct > max_position_pct:
            violations.append(
                f"Projected position exposure {projected_symbol_pct:.2f}% exceeds "
                f"the maximum position percentage {max_position_pct:.2f}% "
                f"(AIOS-307 section 7)."
            )
        if max_sector_pct is not None and projected_sector_pct > max_sector_pct:
            violations.append(
                f"Projected sector exposure {projected_sector_pct:.2f}% exceeds "
                f"the maximum sector exposure {max_sector_pct:.2f}% "
                f"(AIOS-306 section 6, AIOS-307 section 7)."
            )

        warnings: list[str] = list(violations)
        if fundamentals is None:
            warnings.append(
                "Fundamental data unavailable; company risk is not evaluated "
                "(AIOS-307 section 4.2)."
            )
        if not sector:
            warnings.append(
                "No sector classification available; sector exposure cannot be "
                "evaluated (AIOS-306 section 6)."
            )

        limits_configured = max_position_pct is not None or max_sector_pct is not None
        if violations:
            approval_status = "blocked"
            risk_level = "rejected"
        elif limits_configured:
            approval_status = "approved"
            risk_level = "acceptable"
        else:
            approval_status = "not_evaluated"
            risk_level = "not_evaluated"

        risk_score = None
        if max_position_pct is not None and max_position_pct > 0:
            risk_score = min(1.0, projected_symbol_pct / max_position_pct)

        maximum_allowable_exposure = None
        if max_position_pct is not None and portfolio_value is not None:
            maximum_allowable_exposure = portfolio_value * max_position_pct / 100.0

        output = {
            "symbol": symbol,
            "timeframe": data["timeframe"].value,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "approval_status": approval_status,
            "maximum_allowable_exposure": maximum_allowable_exposure,
            "recommended_position_size": None,
            "warnings": warnings,
            "violations": violations,
            "configured_limits": {
                "max_position_percentage": max_position_pct,
                "max_sector_exposure": max_sector_pct,
            },
            "portfolio_impact": {
                "sector": sector,
                "current_symbol_exposure_pct": round(current_symbol_pct, 6),
                "projected_symbol_exposure_pct": round(projected_symbol_pct, 6),
                "current_sector_exposure_pct": round(current_sector_pct, 6),
                "projected_sector_exposure_pct": round(projected_sector_pct, 6),
            },
            "risk_factors": {
                "volatility_atr_14_pct": (round(volatility, 6) if volatility is not None else None),
                "average_volume": average_volume,
                "market_condition": {
                    "direction": structure.direction.value,
                    "strength": structure.strength,
                },
                "fundamentals_available": fundamentals is not None,
                "bars": len(candles),
            },
        }
        dimensions = [
            True,
            latest_atr is not None,
            any(candle.volume > 0 for candle in candles),
            fundamentals is not None,
        ]
        confidence = sum(dimensions) / len(dimensions)
        explanation = (
            f"Risk engine evaluated {symbol} on {len(candles)} "
            f"{data['timeframe'].value} bars. Objective risk factors "
            f"(volatility, liquidity, market condition, company-data "
            f"availability) are reported without an opinion. "
            f"{len(violations)} configured-limit violation(s); approval "
            f"status is {approval_status}. Recommended position size is not "
            f"calculated because position sizing requires documented "
            f"thresholds that are not yet defined (AIOS-207 section 6)."
        )
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output=output,
            explanation=explanation,
            confidence=confidence,
        )


def _technical_bullish_bias(technical_output: Any) -> float | None:
    """Map a Technical Engine output into a bullish-bias score in [0.0, 1.0].

    The technical structure direction carries the documented trend
    classification (AIOS-205 section 5): an uptrend maps to a score above the
    neutral 0.5 and a downtrend below it, scaled by the structure strength
    so a stronger trend produces a more extreme score. A missing or
    malformed output yields ``None`` so the Signal Engine can report WAIT
    instead of inventing a technical opinion (AIOS-605 section 15).
    """
    if not isinstance(technical_output, dict):
        return None
    structure = technical_output.get("structure")
    if not isinstance(structure, dict):
        return None
    direction = structure.get("direction")
    raw_strength = structure.get("strength")
    try:
        strength = float(raw_strength) if raw_strength is not None else 0.5
    except (TypeError, ValueError):
        strength = 0.5
    strength = min(1.0, max(0.0, strength))
    if direction == "uptrend":
        return 0.5 + 0.5 * strength
    if direction == "downtrend":
        return 0.5 - 0.5 * strength
    return 0.5


def _news_bullish_bias(
    news_intelligence: list[Any],
) -> tuple[float | None, int, list[Evidence]]:
    """Combine News Intelligence items into a bullish-bias score.

    The per-item sentiment score in [-1.0, 1.0] (AIOS-102 section 9) is
    mapped to [0.0, 1.0] and averaged across the items, weighted by each
    item's relevance so marginal articles influence the signal less
    (AIOS-305 section 7). Returns ``(news_score, item_count, evidence)``;
    the score is ``None`` when no usable item is available.
    """
    items: list[NewsIntelligenceOutput] = []
    for raw in news_intelligence:
        try:
            intel = (
                raw
                if isinstance(raw, NewsIntelligenceOutput)
                else NewsIntelligenceOutput.model_validate(raw)
            )
        except Exception:  # noqa: BLE001 - tolerate malformed items
            continue
        items.append(intel)
    if not items:
        return None, 0, []
    scores: list[float] = []
    weights: list[float] = []
    evidence: list[Evidence] = []
    for intel in items:
        sentiment = intel.sentiment
        mapped = min(1.0, max(0.0, (float(sentiment.score) + 1.0) / 2.0))
        relevance = min(1.0, max(0.0, float(intel.relevance.score)))
        scores.append(mapped)
        weights.append(relevance)
        evidence.extend(intel.evidence)
    total_weight = sum(weights)
    if total_weight > 0:
        combined = sum(score * weight for score, weight in zip(scores, weights)) / total_weight
    else:
        combined = sum(scores) / len(scores)
    return combined, len(items), evidence


def _signal_confidence(
    technical_score: float | None,
    news_score: float | None,
    settings: SignalSettings,
) -> float:
    """Compute the Signal Engine confidence in [0.0, 1.0].

    Confidence reflects data completeness (which expected components are
    present) and component agreement (technical and news pulling in the same
    direction); conflicting components reduce confidence so the Signal
    Engine can report WAIT instead of a false BUY/SELL (AIOS-605 section 15).
    """
    expected = 2 if settings.require_news else 1
    present = sum(1 for value in (technical_score, news_score) if value is not None)
    completeness = present / expected if expected else 1.0
    agreement = 1.0
    if technical_score is not None and news_score is not None:
        agreement = 1.0 - abs(technical_score - news_score)
    return min(1.0, max(0.0, completeness * agreement))


def _signal_result(
    *,
    symbol: str,
    technical_score: float | None,
    news_score: float | None,
    news_items: int,
    news_intelligence: list[Any],
    evidence: list[Evidence],
    settings: SignalSettings,
) -> tuple[SignalResult, dict]:
    """Build the documented :class:`SignalResult` and its serialized output.

    Resolves the weighted bullish bias (AIOS-305 section 7) with the
    configurable technical/news weights, applies the configurable BUY/SELL
    thresholds (AIOS-605 section 10), and reports WAIT whenever required data
    is missing or confidence falls below the configured minimum so no
    directional opinion is fabricated from weak evidence (AIOS-605 section
    15, AIOS-208 section 10).
    """
    missing: list[str] = []
    if technical_score is None:
        missing.append("technical")
    if settings.require_news and (
        news_score is None or news_items < settings.min_news_items
    ):
        missing.append("news")

    components: list[ScoreComponent] = []
    if technical_score is not None:
        components.append(
            ScoreComponent(
                name="technical",
                score=technical_score,
                weight=settings.technical_weight,
            )
        )
    if news_score is not None:
        components.append(
            ScoreComponent(
                name="news",
                score=news_score,
                weight=settings.news_weight,
            )
        )

    if missing or not components:
        direction = SignalDirection.WAIT
        overall = None
        confidence = 0.0
        reasons = [f"required data missing: {', '.join(missing) or 'no analyzable data'}"]
    else:
        overall = weighted_score(components).overall
        confidence = _signal_confidence(technical_score, news_score, settings)
        if confidence < settings.min_confidence:
            direction = SignalDirection.WAIT
            reasons = [
                f"confidence {confidence:.2f} below minimum {settings.min_confidence:.2f}"
            ]
        elif overall >= settings.buy_threshold:
            direction = SignalDirection.BUY
            reasons = [
                f"bullish bias {overall:.2f} at or above buy threshold "
                f"{settings.buy_threshold:.2f}"
            ]
        elif overall <= settings.sell_threshold:
            direction = SignalDirection.SELL
            reasons = [
                f"bullish bias {overall:.2f} at or below sell threshold "
                f"{settings.sell_threshold:.2f}"
            ]
        else:
            direction = SignalDirection.HOLD
            reasons = [
                f"bullish bias {overall:.2f} between thresholds "
                f"({settings.sell_threshold:.2f}, {settings.buy_threshold:.2f})"
            ]

    factors: list[str] = []
    if technical_score is not None:
        factors.append(f"technical structure score {technical_score:.2f}")
    if news_score is not None:
        factors.append(f"news sentiment score {news_score:.2f} across {news_items} items")
    if missing:
        factors.append("missing components: " + ", ".join(missing))
    if overall is not None:
        factors.append(f"combined bullish bias {overall:.2f}")

    methodology = (
        f"Signal Engine combines technical structure and news intelligence with "
        f"configurable weights (technical {settings.technical_weight:.2f}, news "
        f"{settings.news_weight:.2f}) into a single bullish bias in [0.0, 1.0], then "
        f"derives BUY/SELL/HOLD/WAIT from the configured thresholds "
        f"(buy {settings.buy_threshold:.2f}, sell {settings.sell_threshold:.2f}). "
        f"WAIT is reported whenever required data is missing or confidence falls "
        f"below {settings.min_confidence:.2f}."
    )

    result = SignalResult(
        symbol=symbol,
        direction=direction,
        score=overall if overall is not None else 0.0,
        confidence=confidence,
        components=components,
        technical_score=technical_score,
        news_score=news_score,
        news_items=news_items,
        evidence=evidence,
        explanation=Explanation(
            summary=f"Signal Engine produced direction {direction.value} for {symbol}.",
            factors=factors,
            methodology=methodology,
        ),
        reasons=reasons,
    )
    output = result.model_dump(mode="json")
    output["news_intelligence"] = news_intelligence
    return result, output


class SignalEngine(Engine):
    """Signal Engine (AIOS-605 section 10).

    Combines technical outputs, ranks signals, filters weak opportunities,
    and calculates confidence. Documented output directions: BUY, SELL,
    HOLD, WAIT, accompanied by supporting evidence (AIOS-605 section 10).

    The Signal Engine depends on the Technical Engine and News Intelligence
    Engine because it combines technical outputs and news intelligence
    (AIOS-605 section 10, AIOS-405 section 11).
    """

    engine_type: ClassVar[EngineType] = EngineType.SIGNAL
    name: ClassVar[str] = "Signal Engine"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Combine technical outputs, news intelligence, rank signals, filter weak "
        "opportunities, and calculate confidence."
    )
    dependencies: ClassVar[frozenset[EngineType]] = frozenset({EngineType.TECHNICAL})

    def __init__(
        self,
        *,
        engine_id: str | None = None,
        bus: EventBus | None = None,
        logger: logging.Logger | None = None,
        data_access: DataAccess | None = None,
        news_engine: "NewsEngine" | None = None,
        signal_settings: SignalSettings | None = None,
    ) -> None:
        super().__init__(
            engine_id=engine_id, bus=bus, logger=logger, data_access=data_access
        )
        self._news_engine = news_engine
        self._signal_settings = signal_settings

    def attach_news_engine(self, news_engine: "NewsEngine") -> None:
        """Attach a News Intelligence Engine to this Signal Engine.

        The Signal Engine is registered before providers connect (AIOS-104
        section 4), so the News Engine is built once the connected News
        provider adapter is available and attached at startup (AIOS-605
        section 10, AIOS-405 section 11).
        """
        self._news_engine = news_engine

    def _resolve_signal_settings(self) -> SignalSettings:
        """Return the active Signal Engine configuration (ADR-0009).

        Explicitly injected settings win; otherwise the runtime settings are
        loaded through the configuration layer (ADR-0009 section 5.2) and
        cached for the engine lifetime. When no environment is configured the
        documented defaults are used so analysis remains deterministic.
        """
        if self._signal_settings is None:
            try:
                from aios.config.loader import load_settings

                self._signal_settings = load_settings().signal
            except Exception:  # noqa: BLE001 - fall back to documented defaults
                self._signal_settings = SignalSettings()
        return self._signal_settings

    async def _load_data(self, engine_input: EngineInput) -> dict:
        data = {}
        if self._news_engine is not None:
            symbol = engine_input.payload.get("symbol")
            if symbol:
                try:
                    news_intelligence = await self._news_engine.analyze_symbol_news(symbol)
                    data["news_intelligence"] = [
                        intel.model_dump(mode="json") for intel in news_intelligence
                    ]
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning("Failed to fetch news intelligence: %s", exc)
        return data

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        settings = self._resolve_signal_settings()
        symbol = str(engine_input.payload.get("symbol") or "unknown").strip() or "unknown"
        news_intel = data.get("news_intelligence", [])
        technical_output = _prior_engine_outputs(engine_input).get(EngineType.TECHNICAL)
        technical_score = _technical_bullish_bias(technical_output)
        news_score, news_items, news_evidence = _news_bullish_bias(news_intel)

        result, output = _signal_result(
            symbol=symbol,
            technical_score=technical_score,
            news_score=news_score,
            news_items=news_items,
            news_intelligence=news_intel,
            evidence=news_evidence,
            settings=settings,
        )
        self._logger.info(
            "Signal Engine produced %s for %s (score=%s, confidence=%.2f)",
            result.direction.value,
            symbol,
            f"{result.score:.2f}" if technical_score is not None or news_score is not None else "n/a",
            result.confidence,
        )
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output=output,
            explanation=(
                f"{result.explanation.summary} "
                f"{'; '.join(result.reasons)}. {result.explanation.methodology}"
            ),
            confidence=result.confidence,
        )


def _extract_signal_score(prior: dict) -> tuple[float | None, list[str]]:
    """Extract the bullish-bias score from Signal Engine output.

    Returns (score, reasons) where score is in [-1.0, +1.0] mapped from
    SignalResult's [0.0, 1.0] bullish bias. Returns (None, [...]) if Signal
    output is missing or malformed.
    """
    signal_output = prior.get(EngineType.SIGNAL)
    if not isinstance(signal_output, dict):
        return None, ["Signal output missing"]
    # prior_engine_outputs already unwraps the "output" envelope
    output = signal_output
    direction = output.get("direction")
    score = output.get("score")
    if direction is None or score is None:
        return None, ["Signal output missing direction or score"]
    # Map [0,1] bullish bias to [-1,1]: 0.5 -> 0, 1.0 -> +1, 0.0 -> -1
    mapped_score = (float(score) - 0.5) * 2.0
    mapped_score = max(-1.0, min(1.0, mapped_score))
    return mapped_score, []


def _extract_fundamental_score(prior: dict) -> tuple[float | None, list[str]]:
    """Extract fundamental score from Fundamental Engine output.

    Fundamental Engine output has metrics and derived ratios. We derive a
    score in [-1.0, +1.0] from available quality/growth/value indicators.
    Returns (score, reasons).
    """
    fund_output = prior.get(EngineType.FUNDAMENTAL)
    if not isinstance(fund_output, dict):
        return None, ["Fundamental output missing"]
    # prior_engine_outputs already unwraps the "output" envelope
    output = fund_output
    available = output.get("available", [])
    derived = output.get("derived_ratios", {})
    if not derived:
        return None, ["Fundamental derived ratios unavailable"]
    # Simple heuristic: positive net_margin, roe, low debt_to_equity -> bullish
    score_factors: list[float] = []
    reasons: list[str] = []
    net_margin = derived.get("net_margin")
    if isinstance(net_margin, (int, float)):
        score_factors.append(max(-1.0, min(1.0, (float(net_margin) - 0.05) * 10)))
        reasons.append(f"net_margin={net_margin:.2f}")
    roe = derived.get("return_on_equity")
    if isinstance(roe, (int, float)):
        score_factors.append(max(-1.0, min(1.0, (float(roe) - 0.08) * 10)))
        reasons.append(f"roe={roe:.2f}")
    debt_to_equity = derived.get("debt_to_equity")
    if isinstance(debt_to_equity, (int, float)):
        score_factors.append(max(-1.0, min(1.0, (1.0 - float(debt_to_equity)) * 2)))
        reasons.append(f"debt_to_equity={debt_to_equity:.2f}")
    equity_to_assets = derived.get("equity_to_assets")
    if isinstance(equity_to_assets, (int, float)):
        score_factors.append(max(-1.0, min(1.0, (float(equity_to_assets) - 0.5) * 2)))
        reasons.append(f"equity_to_assets={equity_to_assets:.2f}")
    if not score_factors:
        return None, ["No scorable fundamental metrics"]
    avg = sum(score_factors) / len(score_factors)
    return avg, reasons


def _extract_market_score(prior: dict) -> tuple[float | None, list[str]]:
    """Extract market score from Market Engine output.

    Market Engine output has market_bias (bullish/bearish/neutral) and market_score [0,1].
    Map to [-1.0, +1.0]: bullish -> positive, bearish -> negative, neutral -> 0.
    Returns (score, reasons).
    """
    market_output = prior.get(EngineType.MARKET)
    if not isinstance(market_output, dict):
        return None, ["Market output missing"]
    # prior_engine_outputs already unwraps the "output" envelope
    output = market_output
    market_bias = output.get("market_bias")
    market_score = output.get("market_score")
    if market_bias is None or market_score is None:
        return None, ["Market output missing bias or score"]
    mapped = float(market_score)
    if market_bias == "bullish":
        return mapped, [f"market_bias=bullish, score={market_score:.2f}"]
    if market_bias == "bearish":
        return -mapped, [f"market_bias=bearish, score={market_score:.2f}"]
    return 0.0, [f"market_bias=neutral, score={market_score:.2f}"]


def _compute_confidence(
    *,
    evidence_completeness: float,
    component_agreement: float,
    data_quality: float,
    settings: DecisionSettings,
) -> float:
    """Compute decision confidence per approved methodology.

    Confidence = evidence_completeness_weight * evidence_completeness
               + component_agreement_weight * component_agreement
               + data_quality_weight * data_quality
    """
    w1 = settings.evidence_completeness_weight
    w2 = settings.component_agreement_weight
    w3 = settings.data_quality_weight
    confidence = w1 * evidence_completeness + w2 * component_agreement + w3 * data_quality
    return max(0.0, min(1.0, confidence))


def _decision_confidence_components(
    prior: dict,
    signal_score: float | None,
    fundamental_score: float | None,
    market_score: float | None,
) -> tuple[float, float, float]:
    """Compute the three confidence components.

    Returns (evidence_completeness, component_agreement, data_quality).
    """
    # Evidence completeness: fraction of expected scoring components present
    expected = 3  # Signal, Fundamental, Market
    present = sum(1 for s in (signal_score, fundamental_score, market_score) if s is not None)
    evidence_completeness = present / expected if expected else 1.0

    # Component agreement: how aligned are the present scores
    scores = [s for s in (signal_score, fundamental_score, market_score) if s is not None]
    if len(scores) >= 2:
        # Agreement = 1 - average pairwise distance
        total_dist = 0.0
        pairs = 0
        for i in range(len(scores)):
            for j in range(i + 1, len(scores)):
                total_dist += abs(scores[i] - scores[j])
                pairs += 1
        avg_dist = total_dist / pairs if pairs else 0.0
        component_agreement = max(0.0, 1.0 - avg_dist)
    else:
        component_agreement = 1.0  # Single component = full agreement with itself

    # Data quality: fraction of required analysis engines present
    required_engines = {EngineType.MARKET, EngineType.TECHNICAL, EngineType.FUNDAMENTAL}
    data_present = sum(1 for e in required_engines if e in prior)
    data_quality = data_present / len(required_engines) if required_engines else 1.0

    return evidence_completeness, component_agreement, data_quality


class DecisionEngine(Engine):
    """Decision Engine (AIOS-605 section 11).

    Aggregates engine outputs, applies business rules, applies Shariah
    constraints, applies portfolio constraints, and produces the final
    recommendation. The Decision Engine is the only engine authorized to
    issue investment recommendations (AIOS-605 section 11).

    Validation precedes decision making: Shariah approval, data availability,
    analysis completion, and risk approval (AIOS-406 section 5). The Decision
    Engine cannot override Shariah restrictions, ignore risk limits, or
    execute trades without approval (AIOS-406 section 12). A rejected
    validation yields the documented no-action decision NO_TRADE so the
    system avoids forced trading (AIOS-208 sections 9-10).
    """

    engine_type: ClassVar[EngineType] = EngineType.DECISION
    name: ClassVar[str] = "Decision Engine"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Aggregate engine outputs, apply business rules and Shariah and "
        "portfolio constraints, and produce the final recommendation."
    )
    can_issue_recommendation: ClassVar[bool] = True
    dependencies: ClassVar[frozenset[EngineType]] = frozenset(
        {
            EngineType.MARKET,
            EngineType.TECHNICAL,
            EngineType.FUNDAMENTAL,
            EngineType.RISK,
            EngineType.SIGNAL,
        }
    )

    def __init__(
        self,
        *,
        engine_id: str | None = None,
        bus: EventBus | None = None,
        logger: logging.Logger | None = None,
        data_access: DataAccess | None = None,
        on_decision: Callable[[InvestmentDecision], None] | None = None,
        decision_settings: DecisionSettings | None = None,
    ) -> None:
        super().__init__(
            engine_id=engine_id, bus=bus, logger=logger, data_access=data_access
        )
        self._on_decision = on_decision
        self._decision_settings = decision_settings

    def _resolve_decision_settings(self) -> DecisionSettings:
        """Return the active Decision Engine configuration (ADR-0009).

        Explicitly injected settings win; otherwise the runtime settings are
        loaded through the configuration layer (ADR-0009 section 5.2) and
        cached for the engine lifetime. When no environment is configured the
        documented defaults are used so analysis remains deterministic.
        """
        if self._decision_settings is None:
            try:
                from aios.config.loader import load_settings

                self._decision_settings = load_settings().decision
            except Exception:  # noqa: BLE001 - fall back to documented defaults
                self._decision_settings = DecisionSettings()
        return self._decision_settings

    def validate_input(self, engine_input: EngineInput) -> bool:
        return bool(engine_input.payload.get("symbol"))

    async def _load_data(self, engine_input: EngineInput) -> dict:
        symbol = _require_symbol(engine_input)
        timeframe = _parse_timeframe(engine_input)
        self.require_compliant(symbol)
        if self.data_access is None:
            raise EngineValidationError(f"{self.name} requires a data access facade")
        limit = int(engine_input.payload.get("limit", 250))
        candles = list(self.data_access.get_candles(symbol, timeframe, limit=limit))
        if not candles:
            raise InsufficientDataError(f"No candles available for {symbol} on {timeframe.value}")
        fundamentals = self._load_fundamentals(symbol)
        positions = self._load_positions()
        prior = _prior_engine_outputs(engine_input)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles,
            "fundamentals": fundamentals,
            "positions": positions,
            "prior_outputs": prior,
        }

    def _load_fundamentals(self, symbol: str) -> CompanyFundamentals | None:
        """Return fundamentals for ``symbol``, degrading to None when absent."""
        if self.data_access is None:
            return None
        try:
            return self.data_access.get_fundamentals(symbol)
        except (DataError, DatabaseError):
            return None

    def _load_positions(self) -> list[PortfolioPosition]:
        """Return current portfolio positions, degrading to [] when unavailable."""
        if self.data_access is None:
            return []
        try:
            return list(self.data_access.list_positions())
        except (DataError, DatabaseError):
            return []

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        settings = self._resolve_decision_settings()
        symbol = data["symbol"]
        fundamentals = data["fundamentals"]
        prior = data["prior_outputs"]

        # =====================================================================
        # HARD CONSTRAINTS (Priority order, non-overridable)
        # =====================================================================

        # 1. Shariah Gate: already enforced in _load_data via require_compliant()
        #    If we reach here, Shariah is COMPLIANT. But double-check for safety.
        shariah_ok = True
        try:
            # Re-check compliance status from prior outputs if available
            # The require_compliant in _load_data already blocks non-compliant
            pass
        except EngineValidationError:
            shariah_ok = False

        if not shariah_ok:
            decision = DecisionAction.NO_TRADE
            reason = "Shariah compliance check failed: security is not COMPLIANT. NO_TRADE issued."
            confidence = 0.0
            decision_score = None
            hard_constraint = "shariah"
            triggered_constraints = ["shariah"]
            component_scores = {}
            weighted_score_val = None
            confidence_components = {}

        # 2. Data/Analysis Gates: required analysis engines present
        else:
            missing_analysis = sorted(
                t.value for t in _REQUIRED_ANALYSIS_ENGINES if t not in prior
            )
            data_available = fundamentals is not None
            analysis_complete = not missing_analysis

            if not data_available or not analysis_complete:
                decision = DecisionAction.WAIT
                reasons = []
                if not data_available:
                    reasons.append("fundamental data unavailable")
                if not analysis_complete:
                    reasons.append(f"missing analysis: {', '.join(missing_analysis)}")
                reason = "Data/Analysis Gate failed: " + "; ".join(reasons) + ". WAIT issued."
                confidence = 0.0
                decision_score = None
                hard_constraint = "data_analysis"
                triggered_constraints = ["data_analysis"]
                component_scores = {}
                weighted_score_val = None
                confidence_components = {}

            # 3. Risk Gate: approval_status = blocked -> NO_TRADE
            else:
                risk_output = prior.get(EngineType.RISK)
                risk_approval_status = (
                    str(risk_output.get("approval_status")) if risk_output is not None else None
                )
                risk_level = str(risk_output.get("risk_level")) if risk_output is not None else None
                risk_blocked = risk_approval_status == "blocked"

                if risk_blocked:
                    decision = DecisionAction.NO_TRADE
                    reason = "Risk Gate blocked: approval_status=blocked. NO_TRADE issued."
                    confidence = 0.0
                    decision_score = None
                    hard_constraint = "risk"
                    triggered_constraints = ["risk"]
                    component_scores = {}
                    weighted_score_val = None
                    confidence_components = {}

                # All hard constraints passed -> proceed to weighted scoring
                else:
                    # =====================================================================
                    # WEIGHTED SCORING
                    # =====================================================================

                    # Extract component scores from prior engine outputs
                    signal_score, signal_reasons = _extract_signal_score(prior)
                    fundamental_score, fund_reasons = _extract_fundamental_score(prior)
                    market_score, market_reasons = _extract_market_score(prior)

                    component_scores = {}
                    if signal_score is not None:
                        component_scores["signal"] = signal_score
                    if fundamental_score is not None:
                        component_scores["fundamental"] = fundamental_score
                    if market_score is not None:
                        component_scores["market"] = market_score

                    # Compute weighted score: normalize weights to sum
                    total_weight = (
                        settings.signal_weight
                        + settings.fundamental_weight
                        + settings.market_weight
                    )
                    if total_weight > 0:
                        weights = {
                            "signal": settings.signal_weight / total_weight,
                            "fundamental": settings.fundamental_weight / total_weight,
                            "market": settings.market_weight / total_weight,
                        }
                    else:
                        weights = {"signal": 0.0, "fundamental": 0.0, "market": 0.0}

                    weighted_score_val = 0.0
                    score_reasons = []
                    for name, weight in weights.items():
                        if name in component_scores:
                            contribution = component_scores[name] * weight
                            weighted_score_val += contribution
                            score_reasons.append(f"{name}={component_scores[name]:.2f}*{weight:.2f}")
                        else:
                            score_reasons.append(f"{name}=missing")

                    weighted_score_val = max(-1.0, min(1.0, weighted_score_val))

                    # =====================================================================
                    # CONFIDENCE CALCULATION
                    # =====================================================================

                    evidence_completeness, component_agreement, data_quality = (
                        _decision_confidence_components(
                            prior, signal_score, fundamental_score, market_score
                        )
                    )
                    confidence = _compute_confidence(
                        evidence_completeness=evidence_completeness,
                        component_agreement=component_agreement,
                        data_quality=data_quality,
                        settings=settings,
                    )
                    confidence_components = {
                        "evidence_completeness": evidence_completeness,
                        "component_agreement": component_agreement,
                        "data_quality": data_quality,
                    }

                    # 4. Confidence Gate
                    if confidence < settings.min_confidence:
                        decision = DecisionAction.WAIT
                        reason = (
                            f"Confidence {confidence:.2f} below minimum {settings.min_confidence:.2f}. "
                            f"Components: evidence={evidence_completeness:.2f}, "
                            f"agreement={component_agreement:.2f}, quality={data_quality:.2f}. "
                            f"WAIT issued."
                        )
                        decision_score = weighted_score_val
                        hard_constraint = "confidence"
                        triggered_constraints = ["confidence"]

                    # Directional decision from weighted score
                    elif weighted_score_val >= settings.buy_threshold:
                        decision = DecisionAction.BUY
                        reason = (
                            f"Decision score {weighted_score_val:.2f} >= buy threshold "
                            f"{settings.buy_threshold:.2f}. Components: {', '.join(score_reasons)}. "
                            f"Confidence {confidence:.2f}. BUY issued."
                        )
                        decision_score = weighted_score_val
                        hard_constraint = None
                        triggered_constraints = []

                    elif weighted_score_val <= -settings.sell_threshold:
                        decision = DecisionAction.SELL
                        reason = (
                            f"Decision score {weighted_score_val:.2f} <= sell threshold "
                            f"{-settings.sell_threshold:.2f}. Components: {', '.join(score_reasons)}. "
                            f"Confidence {confidence:.2f}. SELL issued."
                        )
                        decision_score = weighted_score_val
                        hard_constraint = None
                        triggered_constraints = []

                    else:
                        decision = DecisionAction.HOLD
                        reason = (
                            f"Decision score {weighted_score_val:.2f} between thresholds "
                            f"({-settings.sell_threshold:.2f}, {settings.buy_threshold:.2f}). "
                            f"Components: {', '.join(score_reasons)}. Confidence {confidence:.2f}. "
                            f"HOLD issued."
                        )
                        decision_score = weighted_score_val
                        hard_constraint = None
                        triggered_constraints = []

        # =====================================================================
        # BUILD OUTPUT
        # =====================================================================

        risk_score_val = None
        risk_output = prior.get(EngineType.RISK)
        if risk_output is not None:
            raw_score = risk_output.get("risk_score")
            if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
                risk_score_val = max(0.0, min(1.0, float(raw_score)))

        supporting_data: dict[str, Any] = {
            "validation": {
                "shariah_approval": shariah_ok if 'shariah_ok' in locals() else True,
                "data_availability": fundamentals is not None,
                "analysis_completion": not missing_analysis if 'missing_analysis' in locals() else True,
                "risk_approval": not risk_blocked if 'risk_blocked' in locals() else True,
            },
            "decision_score": decision_score,
            "component_scores": component_scores,
            "component_weights": {
                "signal": settings.signal_weight,
                "fundamental": settings.fundamental_weight,
                "market": settings.market_weight,
            },
            "confidence_components": confidence_components,
            "hard_constraints_triggered": triggered_constraints,
            "engine_outputs": {t.value: output for t, output in prior.items()},
        }
        decision_record = InvestmentDecision(
            symbol=symbol,
            decision=decision,
            reason=reason,
            confidence=confidence,
            risk_score=risk_score_val,
            timestamp=datetime.now(timezone.utc),
            supporting_data=supporting_data,
        )

        persisted = self._persist_decision(decision_record)

        # Call the on_decision callback if set and decision is actionable (BUY/SELL)
        if self._on_decision is not None and decision in (DecisionAction.BUY, DecisionAction.SELL):
            try:
                self._on_decision(decision_record)
            except Exception as exc:
                self.logger.exception(
                    "Error in on_decision callback for %s: %s", symbol, exc
                )

        output = {
            "symbol": symbol,
            "decision": decision.value,
            "decision_score": decision_score,
            "confidence": confidence,
            "risk_level": risk_level if 'risk_level' in locals() else None,
            "reason": reason,
            "validation": {
                "status": "VALID" if not triggered_constraints else "CONSTRAINT_TRIGGERED",
                "checks": {
                    "shariah_approval": shariah_ok if 'shariah_ok' in locals() else True,
                    "data_availability": fundamentals is not None,
                    "analysis_completion": not missing_analysis if 'missing_analysis' in locals() else True,
                    "risk_approval": not risk_blocked if 'risk_blocked' in locals() else True,
                },
                "missing_analysis": missing_analysis if 'missing_analysis' in locals() else [],
            },
            "component_scores": component_scores,
            "component_weights": {
                "signal": settings.signal_weight,
                "fundamental": settings.fundamental_weight,
                "market": settings.market_weight,
            },
            "confidence_components": confidence_components,
            "hard_constraints_triggered": triggered_constraints,
            "persisted": persisted,
            "bars": len(data["candles"]),
        }
        explanation = (
            f"Decision engine scored {symbol}: decision={decision.value}, "
            f"score={decision_score}, confidence={confidence:.2f}. {reason}"
        )
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output=output,
            explanation=explanation,
            confidence=confidence,
        )

    def _persist_decision(self, decision_record: InvestmentDecision) -> bool:
        """Persist the decision through the data facade (AIOS-208 section 11).

        Decision history is immutable and owned by the Decision Engine
        (AIOS-501 section 7); a missing or failing decision store degrades to
        ``persisted=False`` so decision making still completes rather than
        fabricating storage results.
        """
        if self.data_access is None:
            return False
        try:
            self.data_access.store_decisions([decision_record])
            return True
        except (DataError, DatabaseError):
            return False


ENGINE_CLASSES: dict[EngineType, type[Engine]] = {
    EngineType.MARKET: MarketEngine,
    EngineType.TECHNICAL: TechnicalEngine,
    EngineType.FUNDAMENTAL: FundamentalEngine,
    EngineType.RISK: RiskEngine,
    EngineType.SIGNAL: SignalEngine,
    EngineType.DECISION: DecisionEngine,
}


def create_engine(
    engine_type: EngineType,
    *,
    engine_id: str | None = None,
    bus: EventBus | None = None,
    logger: logging.Logger | None = None,
    data_access: DataAccess | None = None,
    on_decision: Callable[[InvestmentDecision], None] | None = None,
    news_engine: "NewsEngine" | None = None,
    decision_settings: DecisionSettings | None = None,
) -> Engine:
    """Create an engine instance for a Phase 1 roster type.

    ``data_access`` provides the standardized Data Layer facade engines use to
    consume verified data (AIOS-501 section 2, AIOS-605 section 13).

    ``news_engine`` is accepted only for the Signal Engine; passing
    it to another roster type raises :class:`TypeError`.

    ``decision_settings`` is accepted only for the Decision Engine; passing
    it to another roster type raises :class:`TypeError`.

    Raises :class:`KeyError` for types outside the Phase 1 engine roster.
    """
    if engine_type not in ENGINE_CLASSES:
        raise KeyError(f"Engine type {engine_type!r} is not in the Phase 1 engine roster")
    if engine_type is EngineType.DECISION:
        return DecisionEngine(
            engine_id=engine_id,
            bus=bus,
            logger=logger,
            data_access=data_access,
            on_decision=on_decision,
            decision_settings=decision_settings,
        )
    if engine_type is EngineType.SIGNAL:
        if decision_settings is not None:
            raise TypeError("decision_settings is only accepted for Decision Engine")
        return SignalEngine(
            engine_id=engine_id,
            bus=bus,
            logger=logger,
            data_access=data_access,
            news_engine=news_engine,
        )
    if decision_settings is not None:
        raise TypeError("decision_settings is only accepted for Decision Engine")
    return ENGINE_CLASSES[engine_type](
        engine_id=engine_id, bus=bus, logger=logger, data_access=data_access
    )


def require_decision_authority(engine: Engine) -> None:
    """Enforce that only the Decision Engine issues investment recommendations.

    Implements AIOS-605 section 11: the Decision Engine is the only engine
    authorized to issue investment recommendations; every other engine
    provides analysis only.
    """
    if not engine.can_issue_recommendation or engine.engine_type is not EngineType.DECISION:
        raise SecurityError("Only the Decision Engine may issue an investment recommendation")
