"""Backtesting Framework models (AIOS-707, Phase 9.5).

Provides the core data models for the deterministic backtesting framework.
All models are immutable and follow the project's pydantic conventions.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BacktestStatus(str, Enum):
    """Status of a backtest run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FillPolicy(str, Enum):
    """Order fill policy for backtest execution."""

    EXACT = "exact"          # Fill at exact requested price
    NEXT_OPEN = "next_open"  # Fill at next bar open
    VWAP = "vwap"            # Volume-weighted average price


class SlippageModel(str, Enum):
    """Slippage model for backtest execution."""

    FIXED = "fixed"              # Fixed bps slippage
    VOLUME_WEIGHTED = "volume_weighted"  # Volume-weighted slippage
    SQUARE_ROOT = "square_root"  # Square-root market impact


class TransactionCostConfig(BaseModel):
    """Transaction cost configuration for backtest execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    commission_bps: float = Field(default=10.0, ge=0.0, description="Commission in basis points")
    spread_bps: float = Field(default=5.0, ge=0.0, description="Bid-ask spread in basis points")
    slippage_model: SlippageModel = Field(default=SlippageModel.FIXED)
    slippage_bps: float = Field(default=2.0, ge=0.0, description="Base slippage in basis points")
    fill_policy: FillPolicy = Field(default=FillPolicy.NEXT_OPEN)
    min_fill_fraction: float = Field(default=0.01, ge=0.0, le=1.0, description="Minimum fill fraction")


class BacktestConfig(BaseModel):
    """Immutable backtest configuration snapshot.

    All settings are frozen at backtest start to ensure deterministic replay.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Time range
    start_date: date = Field(description="Backtest start date (inclusive)")
    end_date: date = Field(description="Backtest end date (inclusive)")
    timeframe: str = Field(default="1d", description="Bar timeframe (e.g., '1d', '1h')")

    # Universe
    universe: list[str] = Field(default_factory=list, description="Symbols to include in backtest")

    # Capital
    initial_cash: float = Field(default=100_000.0, gt=0.0, description="Starting paper capital")
    currency: str = Field(default="USD", description="Base currency")

    # Transaction costs
    transaction_costs: TransactionCostConfig = Field(default_factory=TransactionCostConfig)

    # Risk management (from RiskEngine config)
    max_position_pct: float = Field(default=10.0, ge=0.0, le=100.0, description="Max position size as % of equity")
    max_sector_pct: float = Field(default=25.0, ge=0.0, le=100.0, description="Max sector exposure as % of equity")

    # Portfolio allocation (from PortfolioAllocationSettings)
    max_position_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    max_portfolio_exposure: float = Field(default=1.0, ge=0.0, le=1.0)
    max_sector_exposure: float = Field(default=0.25, ge=0.0, le=1.0)
    confidence_scaling: bool = True
    risk_score_scaling: bool = True
    rebalance_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    min_trade_size: float = Field(default=0.01, ge=0.0)

    # Engine config snapshot (for reproducibility)
    engine_config: dict = Field(default_factory=dict, description="Snapshot of engine/portfolio settings at start")

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if info.data.get("start_date") and v < info.data["start_date"]:
            raise ValueError("end_date must be >= start_date")
        return v


class EquityPoint(BaseModel):
    """Single point on the equity curve."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime = Field(description="UTC timestamp of the equity point")
    equity: float = Field(ge=0.0, description="Total equity (cash + positions)")
    cash: float = Field(ge=0.0, description="Available cash")
    market_value: float = Field(ge=0.0, description="Total market value of positions")
    daily_return: float = Field(default=0.0, description="Daily return as fraction")
    cumulative_return: float = Field(default=0.0, description="Cumulative return as fraction")


class PerformanceSnapshot(BaseModel):
    """Complete performance metrics for a backtest run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Returns
    total_return: float = Field(description="Total return as fraction (e.g., 0.15 = 15%)")
    annualized_return: float = Field(description="Annualized return (CAGR)")
    cagr: float = Field(description="Compound Annual Growth Rate")

    # Risk-adjusted
    sharpe_ratio: float = Field(description="Sharpe ratio (risk-free rate = 0)")
    sortino_ratio: float = Field(description="Sortino ratio (downside deviation)")
    calmar_ratio: float = Field(description="Calmar ratio (return / max drawdown)")

    # Drawdown
    max_drawdown: float = Field(ge=0.0, le=1.0, description="Maximum drawdown as fraction")
    avg_drawdown: float = Field(ge=0.0, le=1.0, description="Average drawdown as fraction")
    max_drawdown_duration_days: int = Field(ge=0, description="Max drawdown duration in days")
    recovery_time_days: int = Field(ge=0, description="Average recovery time in days")

    # Trade statistics
    win_rate: float = Field(ge=0.0, le=1.0, description="Fraction of winning trades")
    loss_rate: float = Field(ge=0.0, le=1.0, description="Fraction of losing trades")
    profit_factor: float = Field(ge=0.0, description="Gross profit / gross loss")
    expectancy: float = Field(description="Expected value per trade")
    avg_holding_period_days: float = Field(ge=0.0, description="Average holding period")

    # Exposure
    avg_exposure: float = Field(ge=0.0, le=1.0, description="Average portfolio exposure")
    max_exposure: float = Field(ge=0.0, le=1.0, description="Maximum portfolio exposure")
    avg_position_concentration: float = Field(ge=0.0, le=1.0)
    max_position_concentration: float = Field(ge=0.0, le=1.0)
    avg_sector_concentration: float = Field(ge=0.0, le=1.0)
    max_sector_concentration: float = Field(ge=0.0, le=1.0)

    # Turnover
    portfolio_turnover: float = Field(ge=0.0, description="Annualized portfolio turnover")
    avg_trade_size: float = Field(ge=0.0, description="Average trade size in base currency")

    # Additional
    total_trades: int = Field(ge=0, description="Total number of trades")
    total_fees_paid: float = Field(ge=0.0, description="Total commissions + slippage paid")


class RiskMetrics(BaseModel):
    """Risk-specific metrics for a backtest run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # VaR / CVaR
    var_95: float = Field(description="95% Value at Risk (daily)")
    var_99: float = Field(description="99% Value at Risk (daily)")
    cvar_95: float = Field(description="95% Conditional VaR (Expected Shortfall)")
    cvar_99: float = Field(description="99% Conditional VaR (Expected Shortfall)")

    # Tail risk
    skewness: float = Field(description="Return distribution skewness")
    kurtosis: float = Field(description="Return distribution kurtosis")

    # Correlation / Beta (if benchmark available)
    beta: Optional[float] = Field(default=None, description="Beta vs benchmark")
    correlation: Optional[float] = Field(default=None, description="Correlation vs benchmark")

    # Stress metrics
    worst_day: float = Field(description="Worst single-day return")
    worst_month: float = Field(description="Worst single-month return")
    max_consecutive_losses: int = Field(ge=0, description="Max consecutive losing trades")
    max_consecutive_wins: int = Field(ge=0, description="Max consecutive winning trades")

    # Leverage
    max_leverage: float = Field(ge=1.0, description="Maximum leverage used")
    avg_leverage: float = Field(ge=1.0, description="Average leverage")


class BacktestRun(BaseModel):
    """Persistent backtest run record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(description="Unique run identifier")
    config: BacktestConfig = Field(description="Backtest configuration snapshot")
    status: BacktestStatus = Field(default=BacktestStatus.RUNNING)
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: Optional[datetime] = Field(default=None)
    error: Optional[str] = Field(default=None)

    # Results (populated on completion)
    result: Optional["BacktestResult"] = Field(default=None)


class BacktestResult(BaseModel):
    """Complete backtest result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config: BacktestConfig = Field(description="Backtest configuration")
    started_at: datetime
    completed_at: datetime

    # Equity curve
    equity_curve: list[EquityPoint] = Field(default_factory=list)

    # Trade records
    fills: list["PaperFill"] = Field(default_factory=list)

    # Performance
    performance: PerformanceSnapshot
    risk_metrics: RiskMetrics

    # Decision/Allocation history
    decisions: list["InvestmentDecision"] = Field(default_factory=list)
    allocations: list["PortfolioAllocationResult"] = Field(default_factory=list)

    # Engine metrics
    engine_metrics: dict[str, dict] = Field(default_factory=dict)


# Forward references
from aios.brokers.models import PaperFill
from aios.data.models import InvestmentDecision
from aios.portfolio import PortfolioAllocationResult

BacktestResult.model_rebuild()


# =============================================================================
# Backtest Engine Configuration Models (for config snapshots)
# =============================================================================

class BacktestEngineConfig(BaseModel):
    """Snapshot of engine configuration at backtest start."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Signal Engine
    signal_technical_weight: float
    signal_news_weight: float
    signal_buy_threshold: float
    signal_sell_threshold: float
    signal_min_confidence: float
    signal_min_news_items: int
    signal_require_news: bool

    # Decision Engine
    decision_signal_weight: float
    decision_fundamental_weight: float
    decision_market_weight: float
    decision_buy_threshold: float
    decision_sell_threshold: float
    decision_min_confidence: float
    decision_evidence_completeness_weight: float
    decision_component_agreement_weight: float
    decision_data_quality_weight: float

    # Portfolio Allocation
    portfolio_decision_score_weight: float
    portfolio_signal_score_weight: float
    portfolio_risk_score_weight: float
    portfolio_max_position_weight: float
    portfolio_max_portfolio_exposure: float
    portfolio_max_sector_exposure: float
    portfolio_confidence_scaling: bool
    portfolio_risk_score_scaling: bool
    portfolio_rebalance_threshold: float
    portfolio_min_trade_size: float

    # Risk Engine
    risk_max_position_pct: float
    risk_max_sector_pct: float


# Helper to create engine config snapshot from settings
def create_backtest_engine_config(settings) -> BacktestEngineConfig:
    """Create immutable engine config snapshot from AppSettings."""
    return BacktestEngineConfig(
        # Signal
        signal_technical_weight=settings.signal.technical_weight,
        signal_news_weight=settings.signal.news_weight,
        signal_buy_threshold=settings.signal.buy_threshold,
        signal_sell_threshold=settings.signal.sell_threshold,
        signal_min_confidence=settings.signal.min_confidence,
        signal_min_news_items=settings.signal.min_news_items,
        signal_require_news=settings.signal.require_news,
        # Decision
        decision_signal_weight=settings.decision.signal_weight,
        decision_fundamental_weight=settings.decision.fundamental_weight,
        decision_market_weight=settings.decision.market_weight,
        decision_buy_threshold=settings.decision.buy_threshold,
        decision_sell_threshold=settings.decision.sell_threshold,
        decision_min_confidence=settings.decision.min_confidence,
        decision_evidence_completeness_weight=settings.decision.evidence_completeness_weight,
        decision_component_agreement_weight=settings.decision.component_agreement_weight,
        decision_data_quality_weight=settings.decision.data_quality_weight,
        # Portfolio
        portfolio_decision_score_weight=settings.portfolio.decision_score_weight,
        portfolio_signal_score_weight=settings.portfolio.signal_score_weight,
        portfolio_risk_score_weight=settings.portfolio.risk_score_weight,
        portfolio_max_position_weight=settings.portfolio.max_position_weight,
        portfolio_max_portfolio_exposure=settings.portfolio.max_portfolio_exposure,
        portfolio_max_sector_exposure=settings.portfolio.max_sector_exposure,
        portfolio_confidence_scaling=settings.portfolio.confidence_scaling,
        portfolio_risk_score_scaling=settings.portfolio.risk_score_scaling,
        portfolio_rebalance_threshold=settings.portfolio.rebalance_threshold,
        portfolio_min_trade_size=settings.portfolio.min_trade_size,
        # Risk
        risk_max_position_pct=settings.ingestion.default_exchange,  # placeholder
    )


# =============================================================================
# Phase 9.6 - Strategy Evaluation Models
# =============================================================================

class StrategyClassification(str, Enum):
    """Strategy classification based on evaluation results."""

    FAIL = "fail"
    WEAK = "weak"
    ACCEPTABLE = "acceptable"
    ROBUST = "robust"


class BenchmarkType(str, Enum):
    """Supported benchmark types."""

    BUY_HOLD = "buy_hold"
    SYMBOL = "symbol"
    PORTFOLIO = "portfolio"


class WalkForwardMode(str, Enum):
    """Walk-forward analysis mode."""

    ROLLING = "rolling"
    EXPANDING = "expanding"


class SensitivityResult(BaseModel):
    """Result of parameter sensitivity analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parameter_name: str
    parameter_values: list[float]
    metric_values: list[float]
    best_value: float
    worst_value: float
    median_value: float
    stability_score: float  # 0-1, higher = more stable


class RobustnessScenario(BaseModel):
    """A single robustness test scenario."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    commission_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    execution_delay_bars: int = 0
    min_fill_fraction: float | None = None


class RobustnessResult(BaseModel):
    """Result of robustness analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_performance: PerformanceSnapshot
    scenarios: list[tuple[RobustnessScenario, PerformanceSnapshot]]
    worst_case_drawdown: float
    worst_case_return: float
    degradation_threshold_exceeded: bool


class WalkForwardWindow(BaseModel):
    """Single walk-forward analysis window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    in_sample_performance: PerformanceSnapshot
    out_of_sample_performance: PerformanceSnapshot
    parameters: dict[str, float]


class WalkForwardResult(BaseModel):
    """Complete walk-forward analysis result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    windows: list[WalkForwardWindow]
    aggregate_in_sample: PerformanceSnapshot
    aggregate_out_of_sample: PerformanceSnapshot
    consistency_score: float  # 0-1, how consistent OOS is with IS
    parameter_stability: dict[str, float]  # parameter -> stability score


class OOSValidationResult(BaseModel):
    """Out-of-sample validation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: bool
    train_end: date
    test_start: date
    overlap_detected: bool
    look_ahead_detected: bool
    violations: list[str]


class BenchmarkResult(BaseModel):
    """Benchmark comparison result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_type: BenchmarkType
    benchmark_symbol: str | None
    benchmark_return: float
    benchmark_cagr: float
    benchmark_volatility: float
    benchmark_sharpe: float
    benchmark_max_drawdown: float
    strategy_return: float
    strategy_cagr: float
    strategy_volatility: float
    strategy_sharpe: float
    strategy_max_drawdown: float
    excess_return: float
    excess_cagr: float
    tracking_error: float | None
    information_ratio: float | None
    beta: float | None
    correlation: float | None


class MonteCarloResult(BaseModel):
    """Monte Carlo simulation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    iterations: int
    seed: int
    median_return: float
    percentile_5: float
    percentile_25: float
    percentile_75: float
    percentile_95: float
    worst_case_return: float
    best_case_return: float
    probability_of_loss: float
    probability_of_drawdown_exceeding: dict[float, float]  # threshold -> probability
    median_max_drawdown: float
    drawdown_distribution: list[float]


class StatisticalValidationResult(BaseModel):
    """Statistical validation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sharpe_confidence_interval: tuple[float, float] | None
    return_confidence_interval: tuple[float, float] | None
    max_drawdown_confidence_interval: tuple[float, float] | None
    trade_count: int
    is_statistically_significant: bool
    warnings: list[str]
    sufficient_sample: bool


class StrategyScore(BaseModel):
    """Strategy scoring result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    return_score: float  # 0-100
    risk_score: float
    consistency_score: float
    robustness_score: float
    oos_score: float
    statistical_score: float
    benchmark_score: float
    total_score: float  # 0-100
    breakdown: dict[str, float]


class StrategyEvaluationResult(BaseModel):
    """Complete strategy evaluation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backtest_id: UUID
    evaluated_at: datetime = Field(default_factory=_utc_now)

    # Core evaluation
    performance: PerformanceSnapshot
    risk_metrics: RiskMetrics

    # Benchmark
    benchmark: BenchmarkResult | None = None

    # Walk-forward
    walk_forward: WalkForwardResult | None = None

    # OOS Validation
    oos_validation: OOSValidationResult | None = None

    # Sensitivity
    sensitivity: list[SensitivityResult] = Field(default_factory=list)

    # Robustness
    robustness: RobustnessResult | None = None

    # Regime
    regime_analysis: dict[str, PerformanceSnapshot] = Field(default_factory=dict)

    # Monte Carlo
    monte_carlo: MonteCarloResult | None = None

    # Statistical Validation
    statistical_validation: StatisticalValidationResult | None = None

    # Scoring & Classification
    score: StrategyScore | None = None
    classification: StrategyClassification = StrategyClassification.FAIL

    # Warnings
    warnings: list[str] = Field(default_factory=list)