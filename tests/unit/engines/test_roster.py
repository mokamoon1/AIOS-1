"""Tests for the concrete engine roster (AIOS-605 sections 6-11, Phase 3 wiring)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from aios.analysis.exceptions import InsufficientDataError
from aios.analysis.models import (
    ConfidenceScore,
    Explanation,
    NewsIntelligenceOutput,
    RelevanceAssessment,
    SentimentAssessment,
)
from aios.config.settings import SignalSettings
from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    PortfolioPosition,
    PositionStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.engines.exceptions import EngineStateError, EngineValidationError
from aios.engines.messages import EngineInput, EngineOutput
from aios.engines.roster import (
    ENGINE_CLASSES,
    DecisionEngine,
    FundamentalEngine,
    MarketEngine,
    RiskEngine,
    SignalEngine,
    TechnicalEngine,
    create_engine,
    require_decision_authority,
)
from aios.engines.types import EngineType
from aios.errors import DataError, SecurityError


def _candle(index: int, close: float) -> Candle:
    return Candle(
        timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc),
        symbol="AAPL",
        timeframe=Timeframe.ONE_DAY,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1000.0,
    )


def _uptrend_candles(count: int = 40) -> list[Candle]:
    return [_candle(i, 10.0 + i * 0.5 + (i % 3) * 0.25) for i in range(count)]


def _compliance(status: str = "compliant") -> ShariahCompliance:
    return ShariahCompliance(
        symbol="AAPL",
        company_name="Apple",
        exchange="NASDAQ",
        country="US",
        asset_type=AssetType.EQUITY,
        compliance_status=ComplianceStatus(status),
        provider="test",
        review_date=date(2026, 1, 1),
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31),
        screening_methodology="test",
        screening_date=date(2026, 1, 1),
    )


def _fundamentals() -> CompanyFundamentals:
    return CompanyFundamentals(
        symbol="AAPL",
        sector="Technology",
        industry="Hardware",
        revenue=1000.0,
        net_income=150.0,
        eps=1.5,
        assets=2000.0,
        liabilities=800.0,
        cash_flow=250.0,
        equity=1200.0,
        report_date=date(2026, 6, 30),
    )


def _position(symbol: str, allocation: float, sector: str = "Technology") -> PortfolioPosition:
    return PortfolioPosition(
        symbol=symbol,
        exchange="NASDAQ",
        quantity=1.0,
        entry_price=10.0,
        current_price=10.0,
        allocation=allocation,
        sector=sector,
        status=PositionStatus.OPEN,
    )


class _FakeDataAccess:
    def __init__(
        self,
        *,
        candles: list[Candle] | None = None,
        compliance: str = "compliant",
        fundamentals: CompanyFundamentals | None = None,
        positions: list[PortfolioPosition] | None = None,
        store_failure: bool = False,
    ) -> None:
        self._candles = candles or []
        self._compliance = compliance
        self._fundamentals = fundamentals
        self._positions = positions or []
        self._stored_decisions: list = []
        self._store_failure = store_failure

    def get_candles(self, symbol, timeframe, *, start=None, end=None, limit=1000) -> list[Candle]:
        return self._candles

    def get_fundamentals(self, symbol, *, report_date=None) -> CompanyFundamentals:
        if self._fundamentals is None:
            raise DataError("no fundamentals")
        return self._fundamentals

    def get_compliance_status(self, symbol, *, as_of=None) -> ShariahCompliance:
        return _compliance(self._compliance)

    def list_positions(self, *, status=None) -> list[PortfolioPosition]:
        if status is None:
            return self._positions
        return [p for p in self._positions if p.status is status]

    def store_decisions(self, decisions: list) -> int:
        if self._store_failure:
            raise DataError("storage unavailable")
        self._stored_decisions.extend(decisions)
        return len(decisions)


def _engine_input() -> EngineInput:
    return EngineInput(request_id="req-1", payload={"symbol": "AAPL"})


async def _analyze(engine, engine_input: EngineInput) -> EngineOutput:
    data = await engine._load_data(engine_input)
    return await engine._analyze(engine_input, data)


def _news_intel(sentiment_score: float, *, relevance: float = 0.8) -> dict:
    intel = NewsIntelligenceOutput(
        article_id="a1",
        symbol="AAPL",
        provider="mock_news",
        published_at=datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc),
        relevance=RelevanceAssessment(
            score=relevance,
            rationale=f"Relevance {relevance}",
            evidence=["AAPL in symbols"],
            explanation=Explanation(
                summary="relevant", factors=["AAPL"], methodology="test"
            ),
        ),
        sentiment=SentimentAssessment(
            label=(
                "BULLISH"
                if sentiment_score > 0
                else "BEARISH" if sentiment_score < 0 else "NEUTRAL"
            ),
            score=sentiment_score,
            confidence=0.9,
            methodology="test",
            evidence=[],
            explanation=Explanation(
                summary="sentiment", factors=[], methodology="test"
            ),
        ),
        confidence=ConfidenceScore(score=0.9, rationale="test", factors=["test"]),
        evidence=[],
        explanation=Explanation(
            summary="intel", factors=[], methodology="test"
        ),
    )
    return intel.model_dump(mode="json")


def _technical_output(direction: str, strength: float) -> dict:
    return {"structure": {"direction": direction, "strength": strength}}


def _signal_engine_input(*, technical: dict | None = None) -> EngineInput:
    payload: dict = {"symbol": "AAPL"}
    if technical is not None:
        payload["engine_outputs"] = {"technical": {"output": technical}}
    return EngineInput(request_id="req-signal", payload=payload)


async def _signal_analyze(
    engine: SignalEngine, engine_input: EngineInput, news: list | None = None
) -> EngineOutput:
    data = {"news_intelligence": news or []}
    return await engine._analyze(engine_input, data)


def test_engine_classes_cover_full_roster() -> None:
    assert set(ENGINE_CLASSES) == set(EngineType)


def test_create_engine_returns_matching_type() -> None:
    for engine_type, engine_class in ENGINE_CLASSES.items():
        engine = create_engine(engine_type)
        assert isinstance(engine, engine_class)
        assert engine.engine_type is engine_type
        assert engine.state.value == "uninitialized"


def test_create_engine_accepts_engine_id() -> None:
    engine = create_engine(EngineType.MARKET, engine_id="market-1")
    assert engine.engine_id == "market-1"


def test_create_engine_accepts_data_access() -> None:
    data_access = _FakeDataAccess(candles=_uptrend_candles())
    engine = create_engine(EngineType.TECHNICAL, data_access=data_access)
    assert engine.data_access is data_access


async def test_market_engine_analysis() -> None:
    engine = MarketEngine(data_access=_FakeDataAccess(candles=_uptrend_candles()))
    engine.initialize()
    result = await _analyze(engine, _engine_input())
    assert result.output["symbol"] == "AAPL"
    assert result.output["bars"] == 40
    assert result.output["market_bias"] in {"bullish", "bearish", "neutral"}
    assert 0.0 <= result.output["market_score"] <= 1.0
    assert result.output["volatility"]["atr_14"] > 0
    assert result.engine_type is EngineType.MARKET


async def test_technical_engine_analysis() -> None:
    engine = TechnicalEngine(data_access=_FakeDataAccess(candles=_uptrend_candles()))
    engine.initialize()
    result = await _analyze(engine, _engine_input())
    output = result.output
    assert output["structure"]["direction"] in {"uptrend", "downtrend", "range"}
    assert 0.0 <= output["structure"]["strength"] <= 1.0
    assert output["indicators"]["rsi_14"] is not None
    assert 0.0 <= output["indicators"]["rsi_14"] <= 100.0
    assert output["indicators"]["macd_12_26_9"]["line"] is not None
    assert output["indicators"]["bollinger_20_2"]["upper"] is not None
    assert output["bars"] == 40


async def test_fundamental_engine_analysis() -> None:
    engine = FundamentalEngine(
        data_access=_FakeDataAccess(fundamentals=_fundamentals(), candles=_uptrend_candles())
    )
    engine.initialize()
    result = await _analyze(engine, _engine_input())
    output = result.output
    assert output["symbol"] == "AAPL"
    assert output["metrics"]["revenue"] == 1000.0
    assert output["derived_ratios"]["net_margin"] == pytest.approx(0.15)
    assert output["derived_ratios"]["return_on_equity"] == pytest.approx(0.125)
    assert output["derived_ratios"]["debt_to_equity"] == pytest.approx(800 / 1200)
    assert output["derived_ratios"]["equity_to_assets"] == pytest.approx(1200 / 2000)
    assert "revenue" in output["available"]


async def test_engines_require_data_access() -> None:
    for engine_class in (
        MarketEngine,
        TechnicalEngine,
        FundamentalEngine,
        RiskEngine,
        DecisionEngine,
    ):
        engine = engine_class()
        engine.initialize()
        with pytest.raises(EngineValidationError):
            await engine._load_data(_engine_input())


async def test_engine_blocks_non_compliant_security() -> None:
    engine = MarketEngine(data_access=_FakeDataAccess(compliance="non_compliant"))
    engine.initialize()
    with pytest.raises(EngineValidationError):
        await engine._load_data(_engine_input())


async def test_engine_blocks_unknown_compliance() -> None:
    engine = TechnicalEngine(data_access=_FakeDataAccess(compliance="unknown"))
    engine.initialize()
    with pytest.raises(EngineValidationError):
        await engine._load_data(_engine_input())


async def test_engine_rejects_insufficient_data() -> None:
    engine = TechnicalEngine(data_access=_FakeDataAccess(candles=[]))
    engine.initialize()
    with pytest.raises(InsufficientDataError):
        await engine._load_data(_engine_input())


async def test_engine_rejects_missing_symbol() -> None:
    engine = TechnicalEngine(data_access=_FakeDataAccess(candles=_uptrend_candles()))
    engine.initialize()
    with pytest.raises(EngineValidationError):
        await engine._load_data(EngineInput(request_id="req-2", payload={}))


async def test_risk_engine_reports_objective_factors() -> None:
    engine = RiskEngine(
        data_access=_FakeDataAccess(candles=_uptrend_candles(), fundamentals=_fundamentals())
    )
    engine.initialize()
    result = await _analyze(engine, _engine_input())
    output = result.output
    assert output["symbol"] == "AAPL"
    assert output["timeframe"] == "1d"
    assert output["risk_level"] == "not_evaluated"
    assert output["approval_status"] == "not_evaluated"
    assert output["risk_score"] is None
    assert output["maximum_allowable_exposure"] is None
    assert output["recommended_position_size"] is None
    assert output["configured_limits"] == {
        "max_position_percentage": None,
        "max_sector_exposure": None,
    }
    assert output["risk_factors"]["volatility_atr_14_pct"] is not None
    assert output["risk_factors"]["average_volume"] > 0
    assert output["risk_factors"]["fundamentals_available"] is True
    assert output["risk_factors"]["market_condition"]["direction"] in {
        "uptrend",
        "downtrend",
        "range",
    }
    assert output["portfolio_impact"]["projected_symbol_exposure_pct"] == 0.0
    assert "not yet defined" in result.explanation
    assert result.engine_type is EngineType.RISK
    assert result.confidence > 0.0


async def test_risk_engine_blocks_over_maximum_position() -> None:
    engine = RiskEngine(
        data_access=_FakeDataAccess(
            candles=_uptrend_candles(),
            fundamentals=_fundamentals(),
            positions=[_position("AAPL", allocation=0.60)],
        )
    )
    engine.initialize()
    result = await _analyze(
        engine,
        EngineInput(
            request_id="req-3",
            payload={
                "symbol": "AAPL",
                "max_position_percentage": 50,
                "requested_position_percentage": 10,
            },
        ),
    )
    output = result.output
    assert output["risk_level"] == "rejected"
    assert output["approval_status"] == "blocked"
    assert output["risk_score"] == 1.0
    assert output["portfolio_impact"]["current_symbol_exposure_pct"] == 60.0
    assert output["portfolio_impact"]["projected_symbol_exposure_pct"] == 70.0
    assert "exceeds" in output["violations"][0]


async def test_risk_engine_approves_within_configured_limits() -> None:
    engine = RiskEngine(
        data_access=_FakeDataAccess(
            candles=_uptrend_candles(),
            fundamentals=_fundamentals(),
            positions=[_position("MSFT", allocation=0.10)],
        )
    )
    engine.initialize()
    result = await _analyze(
        engine,
        EngineInput(
            request_id="req-4",
            payload={
                "symbol": "AAPL",
                "max_position_percentage": 30,
                "max_sector_exposure": 60,
                "portfolio_value": 100000,
            },
        ),
    )
    output = result.output
    assert output["risk_level"] == "acceptable"
    assert output["approval_status"] == "approved"
    assert output["risk_score"] == 0.0
    assert output["maximum_allowable_exposure"] == 30000.0
    assert output["violations"] == []
    assert output["portfolio_impact"]["sector"] == "Technology"
    assert output["portfolio_impact"]["projected_sector_exposure_pct"] == 10.0


async def test_risk_engine_warns_on_missing_fundamentals() -> None:
    engine = RiskEngine(data_access=_FakeDataAccess(candles=_uptrend_candles()))
    engine.initialize()
    result = await _analyze(engine, _engine_input())
    output = result.output
    assert output["risk_factors"]["fundamentals_available"] is False
    assert any("Fundamental data unavailable" in warning for warning in output["warnings"])


async def test_risk_engine_rejects_invalid_limit_payload() -> None:
    engine = RiskEngine(data_access=_FakeDataAccess(candles=_uptrend_candles()))
    engine.initialize()
    with pytest.raises(EngineValidationError):
        await _analyze(
            engine,
            EngineInput(
                request_id="req-5",
                payload={"symbol": "AAPL", "max_position_percentage": "ten"},
            ),
        )


def _prior_outputs(*, risk_status: str | None = "approved") -> dict:
    outputs = {
        "market": {"market_bias": "bullish", "market_score": 0.8},
        "technical": {"structure": {"direction": "uptrend", "strength": 0.7}},
        "fundamental": {"symbol": "AAPL", "available": ["revenue"]},
    }
    if risk_status is not None:
        risk_level = {
            "approved": "acceptable",
            "acceptable": "acceptable",
            "not_evaluated": "not_evaluated",
            "blocked": "rejected",
            "rejected": "rejected",
        }.get(risk_status, risk_status)
        outputs["risk"] = {
            "approval_status": risk_status,
            "risk_level": risk_level,
            "risk_score": 0.4,
        }
    return outputs


def _decision_engine(*, risk_status: str | None = "approved") -> DecisionEngine:
    data_access = _FakeDataAccess(candles=_uptrend_candles(), fundamentals=_fundamentals())
    engine = DecisionEngine(data_access=data_access)
    engine.initialize()
    return engine


async def _analyze_decision(engine: DecisionEngine, prior_outputs: dict) -> EngineOutput:
    return await _analyze(
        engine,
        EngineInput(
            request_id="req-d",
            payload={"symbol": "AAPL", "engine_outputs": prior_outputs},
        ),
    )


async def test_decision_engine_rejects_missing_analysis() -> None:
    engine = _decision_engine()
    result = await _analyze_decision(engine, {"risk": {"approval_status": "approved"}})
    output = result.output
    # Missing analysis -> WAIT (data/analysis gate)
    assert output["decision"] == "wait"
    assert output["validation"]["status"] == "CONSTRAINT_TRIGGERED"
    assert output["validation"]["checks"]["analysis_completion"] is False
    assert "market" in output["validation"]["missing_analysis"]
    assert "technical" in output["validation"]["missing_analysis"]
    assert "fundamental" in output["validation"]["missing_analysis"]
    assert output["persisted"] is True
    assert "data_analysis" in output["hard_constraints_triggered"]


async def test_decision_engine_missing_risk_approval_gate_passes() -> None:
    """Risk gate only blocks on 'blocked' status; missing/None passes."""
    engine = _decision_engine()
    result = await _analyze_decision(engine, _prior_outputs(risk_status=None))
    output = result.output
    # Risk missing -> risk_output=None -> not blocked -> gate passes
    # All hard constraints pass -> weighted scoring
    # component scores: market=0.8, fundamental=None (no derived_ratios), signal=None
    # weighted = 0.8 * 0.2 = 0.16 -> HOLD (between -0.65 and 0.65)
    assert output["decision"] == "hold"
    assert output["validation"]["status"] == "VALID"
    assert output["decision_score"] is not None
    assert output["risk_level"] is None
    assert output["persisted"] is True


async def test_decision_engine_unapproved_risk_not_blocked() -> None:
    """Risk gate only blocks on 'blocked'; 'not_evaluated' passes."""
    engine = _decision_engine()
    result = await _analyze_decision(engine, _prior_outputs(risk_status="not_evaluated"))
    output = result.output
    # Risk not_evaluated -> not blocked -> gate passes
    # All hard constraints pass -> weighted scoring -> HOLD
    assert output["decision"] == "hold"
    assert output["validation"]["status"] == "VALID"
    assert output["decision_score"] is not None
    assert output["risk_level"] == "not_evaluated"
    assert output["persisted"] is True


async def test_decision_engine_blocked_risk_issues_no_trade() -> None:
    """Risk gate blocks only when approval_status == 'blocked'."""
    engine = _decision_engine()
    result = await _analyze_decision(engine, _prior_outputs(risk_status="blocked"))
    output = result.output
    # Risk blocked -> NO_TRADE (hard constraint)
    assert output["decision"] == "no_trade"
    assert output["validation"]["status"] == "CONSTRAINT_TRIGGERED"
    assert output["risk_level"] == "rejected"
    assert "risk" in output["hard_constraints_triggered"]
    assert output["persisted"] is True


async def test_decision_engine_issues_directional_decision_when_validated() -> None:
    """When all gates pass, Decision Engine produces BUY/SELL/HOLD based on score."""
    engine = _decision_engine()
    result = await _analyze_decision(engine, _prior_outputs())
    output = result.output
    # All hard constraints pass -> weighted scoring
    # component scores: market=0.8, fundamental=None, signal=None
    # weighted = 0.8 * 0.2 = 0.16 -> HOLD
    assert output["decision"] == "hold"
    assert output["validation"]["status"] == "VALID"
    assert output["validation"]["checks"] == {
        "shariah_approval": True,
        "data_availability": True,
        "analysis_completion": True,
        "risk_approval": True,
    }
    assert output["decision_score"] is not None
    assert output["risk_level"] == "acceptable"
    assert output["persisted"] is True
    assert "not yet defined" not in output["reason"]


async def test_decision_engine_persists_decision_record() -> None:
    data_access = _FakeDataAccess(candles=_uptrend_candles(), fundamentals=_fundamentals())
    engine = DecisionEngine(data_access=data_access)
    engine.initialize()
    await _analyze_decision(engine, _prior_outputs())
    assert len(data_access._stored_decisions) == 1
    record = data_access._stored_decisions[0]
    assert record.symbol == "AAPL"
    assert record.decision.value == "hold"  # Now produces HOLD, not WAIT
    assert record.risk_score == 0.4
    assert "validation" in record.supporting_data
    assert "engine_outputs" in record.supporting_data
    assert "component_scores" in record.supporting_data
    assert "confidence_components" in record.supporting_data


async def test_decision_engine_degrades_when_store_fails() -> None:
    data_access = _FakeDataAccess(
        candles=_uptrend_candles(), fundamentals=_fundamentals(), store_failure=True
    )
    engine = DecisionEngine(data_access=data_access)
    engine.initialize()
    result = await _analyze_decision(engine, _prior_outputs())
    assert result.output["persisted"] is False
    assert result.output["decision"] == "hold"  # Now produces HOLD


async def test_decision_engine_ignores_unknown_prior_outputs() -> None:
    engine = _decision_engine()
    result = await _analyze_decision(
        engine,
        {
            **_prior_outputs(),
            "decision": {"decision": "sell"},
            "garbage": {"unrelated": True},
        },
    )
    assert result.output["validation"]["status"] == "VALID"


async def test_signal_engine_scaffold_output() -> None:
    engine = SignalEngine()
    engine.initialize()
    result = await _analyze(engine, _engine_input())
    assert "signal" in result.explanation.lower()


async def test_signal_engine_buy_on_uptrend_and_bullish_news() -> None:
    engine = SignalEngine()
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("uptrend", 1.0)),
        news=[_news_intel(0.9, relevance=1.0)],
    )
    output = result.output
    assert output["direction"] == "buy"
    assert output["score"] >= 0.65
    assert output["confidence"] >= 0.5
    assert output["news_items"] == 1
    assert output["technical_score"] is not None
    assert output["news_score"] is not None
    assert output["reasons"]
    assert "signal" in result.explanation.lower()


async def test_signal_engine_sell_on_downtrend_and_bearish_news() -> None:
    engine = SignalEngine()
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("downtrend", 1.0)),
        news=[_news_intel(-0.9, relevance=1.0)],
    )
    assert result.output["direction"] == "sell"
    assert result.output["score"] <= 0.35


async def test_signal_engine_hold_on_neutral_inputs() -> None:
    engine = SignalEngine()
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("range", 0.5)),
        news=[_news_intel(0.0, relevance=1.0)],
    )
    assert result.output["direction"] == "hold"
    assert 0.35 < result.output["score"] < 0.65


async def test_signal_engine_wait_when_technical_missing() -> None:
    engine = SignalEngine()
    engine.initialize()
    result = await _signal_analyze(engine, _signal_engine_input(), news=[_news_intel(0.9)])
    assert result.output["direction"] == "wait"
    assert result.output["score"] == 0.0
    assert any("technical" in reason for reason in result.output["reasons"])


async def test_signal_engine_wait_when_news_missing() -> None:
    engine = SignalEngine()
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("uptrend", 1.0)),
    )
    assert result.output["direction"] == "wait"
    assert any("news" in reason for reason in result.output["reasons"])


async def test_signal_engine_wait_on_conflicting_low_confidence() -> None:
    engine = SignalEngine()
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("uptrend", 0.8)),
        news=[_news_intel(-0.6, relevance=1.0)],
    )
    assert result.output["direction"] == "wait"
    assert any("confidence" in reason for reason in result.output["reasons"])


async def test_signal_engine_uses_configurable_thresholds() -> None:
    settings = SignalSettings(
        technical_weight=0.7,
        news_weight=0.3,
        buy_threshold=0.4,
        sell_threshold=0.2,
        min_confidence=0.5,
        min_news_items=1,
        require_news=True,
    )
    engine = SignalEngine(signal_settings=settings)
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("range", 0.5)),
        news=[_news_intel(0.0, relevance=1.0)],
    )
    assert result.output["direction"] == "buy"


async def test_signal_engine_respects_min_news_items() -> None:
    settings = SignalSettings(
        technical_weight=0.7,
        news_weight=0.3,
        buy_threshold=0.65,
        sell_threshold=0.35,
        min_confidence=0.5,
        min_news_items=2,
        require_news=True,
    )
    engine = SignalEngine(signal_settings=settings)
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("uptrend", 1.0)),
        news=[_news_intel(0.9, relevance=1.0)],
    )
    assert result.output["direction"] == "wait"
    assert any("news" in reason for reason in result.output["reasons"])


async def test_signal_engine_technical_only_when_news_not_required() -> None:
    settings = SignalSettings(
        technical_weight=0.7,
        news_weight=0.3,
        buy_threshold=0.65,
        sell_threshold=0.35,
        min_confidence=0.5,
        min_news_items=1,
        require_news=False,
    )
    engine = SignalEngine(signal_settings=settings)
    engine.initialize()
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("uptrend", 1.0)),
    )
    assert result.output["direction"] == "buy"
    assert result.output["news_score"] is None
    assert result.output["technical_score"] == pytest.approx(1.0)


async def test_signal_engine_output_carries_structured_fields() -> None:
    engine = SignalEngine()
    engine.initialize()
    news = [_news_intel(0.9, relevance=1.0)]
    result = await _signal_analyze(
        engine,
        _signal_engine_input(technical=_technical_output("uptrend", 1.0)),
        news=news,
    )
    output = result.output
    assert output["symbol"] == "AAPL"
    assert output["direction"] in {"buy", "sell", "hold", "wait"}
    assert 0.0 <= output["score"] <= 1.0
    assert 0.0 <= output["confidence"] <= 1.0
    assert isinstance(output["reasons"], list) and output["reasons"]
    assert output["news_intelligence"] == news


def test_signal_engine_depends_on_technical() -> None:
    assert SignalEngine.dependencies == frozenset({EngineType.TECHNICAL})


def test_decision_engine_depends_on_all_analysis_engines() -> None:
    assert DecisionEngine.dependencies == frozenset(
        {
            EngineType.MARKET,
            EngineType.TECHNICAL,
            EngineType.FUNDAMENTAL,
            EngineType.RISK,
            EngineType.SIGNAL,
        }
    )


def test_decision_engine_is_only_recommendation_authority() -> None:
    decision = DecisionEngine()
    require_decision_authority(decision)
    assert decision.can_issue_recommendation is True


def test_require_decision_authority_rejects_other_engines() -> None:
    other_engines = (
        MarketEngine,
        TechnicalEngine,
        FundamentalEngine,
        RiskEngine,
        SignalEngine,
    )
    for engine_class in other_engines:
        with pytest.raises(SecurityError):
            require_decision_authority(engine_class())


def test_engine_full_lifecycle() -> None:
    engine = create_engine(EngineType.DECISION)
    assert engine.state.value == "uninitialized"
    engine.initialize()
    assert engine.state.value == "initialized"
    engine.shutdown()
    assert engine.state.value == "shutdown"
    with pytest.raises(EngineStateError):
        engine.initialize()
