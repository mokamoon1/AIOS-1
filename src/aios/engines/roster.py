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
    atr,
    bollinger_bands,
    ema,
    fibonacci_levels,
    macd,
    market_bias,
    market_structure,
    rsi,
    sma,
)
from aios.analysis.exceptions import InsufficientDataError
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


class SignalEngine(Engine):
    """Signal Engine (AIOS-605 section 10).

    Combines technical outputs, ranks signals, filters weak opportunities,
    and calculates confidence. Documented output directions: BUY, SELL,
    HOLD, WAIT, accompanied by supporting evidence (AIOS-605 section 10).

    The Signal Engine depends on the Technical Engine because it combines
    technical outputs (AIOS-605 section 10, AIOS-405 section 11).
    """

    engine_type: ClassVar[EngineType] = EngineType.SIGNAL
    name: ClassVar[str] = "Signal Engine"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Combine technical outputs, rank signals, filter weak "
        "opportunities, and calculate confidence."
    )
    dependencies: ClassVar[frozenset[EngineType]] = frozenset({EngineType.TECHNICAL})

    async def _load_data(self, engine_input: EngineInput) -> dict:
        return {}

    async def _analyze(self, engine_input: EngineInput, data: dict) -> EngineOutput:
        return EngineOutput(
            engine_type=self.engine_type,
            engine_id=self.engine_id,
            request_id=engine_input.request_id,
            output=_scaffold_output(engine_input.request_id),
            explanation=(
                "Signal engine registered. Signal direction and evidence "
                "computation is wired in a later phase (AIOS-605 section 10)."
            ),
            confidence=0.0,
        )


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
    ) -> None:
        super().__init__(
            engine_id=engine_id, bus=bus, logger=logger, data_access=data_access
        )
        self._on_decision = on_decision

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
        symbol = data["symbol"]
        fundamentals = data["fundamentals"]
        prior = data["prior_outputs"]

        present = set(prior)
        missing_analysis = sorted(t.value for t in _REQUIRED_ANALYSIS_ENGINES if t not in present)
        risk_output = prior.get(EngineType.RISK)
        risk_approval_status = (
            str(risk_output.get("approval_status")) if risk_output is not None else None
        )
        risk_level = str(risk_output.get("risk_level")) if risk_output is not None else None
        risk_approved = risk_approval_status in {"approved", "acceptable"}

        validation = {
            "shariah_approval": True,
            "data_availability": fundamentals is not None,
            "analysis_completion": not missing_analysis,
            "risk_approval": risk_approved,
        }
        failed_gates = [gate for gate, ok in validation.items() if not ok]
        validation_status = "VALID" if not failed_gates else "REJECTED"

        if failed_gates:
            decision = DecisionAction.NO_TRADE
            reason = (
                f"Decision validation rejected: {', '.join(failed_gates)}. "
                f"Missing analysis: {', '.join(missing_analysis) or 'none'}. "
                f"No trade is issued to avoid forced or unsafe trading "
                f"(AIOS-208 sections 9-10)."
            )
        else:
            decision = DecisionAction.WAIT
            reason = (
                "All decision validation gates passed (Shariah approval, "
                "data availability, analysis completion, risk approval). The "
                "final direction requires documented/configurable scoring "
                "weights (AIOS-406 section 6) that are not yet defined, so "
                "the engine issues the no-action WAIT to avoid forced "
                "trading (AIOS-208 section 10)."
            )

        risk_score = None
        if risk_output is not None:
            raw_score = risk_output.get("risk_score")
            if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
                risk_score = max(0.0, min(1.0, float(raw_score)))

        checks = list(validation.values())
        confidence = sum(checks) / len(checks) if checks else 0.0

        supporting_data: dict[str, Any] = {
            "validation": validation,
            "decision_score": None,
            "engine_outputs": {t.value: output for t, output in prior.items()},
        }
        decision_record = InvestmentDecision(
            symbol=symbol,
            decision=decision,
            reason=reason,
            confidence=confidence,
            risk_score=risk_score,
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
            "decision_score": None,
            "confidence": confidence,
            "risk_level": risk_level,
            "reason": reason,
            "validation": {
                "status": validation_status,
                "checks": validation,
                "missing_analysis": missing_analysis,
            },
            "persisted": persisted,
            "bars": len(data["candles"]),
        }
        explanation = (
            f"Decision engine validated {symbol}: {validation_status} "
            f"({', '.join(f'{gate}={ok}' for gate, ok in validation.items())}). "
            f"Decision is {decision.value}; score weighting and directional "
            f"rules remain configurable placeholders (AIOS-406 sections 6-7)."
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
) -> Engine:
    """Create an engine instance for a Phase 1 roster type.

    ``data_access`` provides the standardized Data Layer facade engines use to
    consume verified data (AIOS-501 section 2, AIOS-605 section 13).

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
        )
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
