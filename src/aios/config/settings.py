"""Runtime settings model and environment enumeration.

Implements the application configuration foundation defined in ADR-0008 and
ADR-0009:
    - pydantic-settings as the configuration framework (ADR-0008 section 5.1).
    - Four operational environments (ADR-0009 section 5.8).
    - Environment variables override configuration files and default values
      (ADR-0009 section 5.2).
    - Secrets, including the database password, are provided exclusively
      through environment variables (ADR-0009 section 5.6).
    - Logging foundation per ADR-0010 (levels, formatter, destination).
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from aios.providers.registry import ProvidersConfig

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class Environment(str, Enum):
    """Supported operational environments (ADR-0009 section 5.8)."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    BACKTEST = "backtest"
    PAPER = "paper"
    PRODUCTION = "production"


class LoggingFormat(str, Enum):
    """Structured logging output formats (ADR-0010 section 5.2).

    Production and Paper Trading use the machine-readable ``json`` format;
    Development and Testing use ``human`` for readability.
    """

    HUMAN = "human"
    JSON = "json"


class LoggingDestination(str, Enum):
    """Log output destination (ADR-0010 section 5.6).

    Development and Testing log to the console; Paper Trading and Production
    use rotating log files.
    """

    CONSOLE = "console"
    FILE = "file"


class LoggingSettings(BaseSettings):
    """Logging configuration per environment (ADR-0010).

    The formatter is selected through the environment configuration defined
    by ADR-0009. Environment variables with the ``AIOS_LOGGING_`` prefix
    override configuration file values (ADR-0009 section 5.2). No secrets
    may ever be written to logs (ADR-0010 section 5.7); the logging layer
    applies sensitive-data masking.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_LOGGING_", extra="ignore")

    level: str = "INFO"
    format: LoggingFormat = LoggingFormat.HUMAN
    destination: LoggingDestination = LoggingDestination.CONSOLE
    file_path: str = "logs/aios.log"
    file_max_bytes: int = 10_000_000
    file_backup_count: int = 5

    @field_validator("level")
    @classmethod
    def level_must_be_supported(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _LOG_LEVELS:
            raise ValueError(
                f"Unsupported logging level {value!r}. "
                f"Valid values: {', '.join(sorted(_LOG_LEVELS))}."
            )
        return normalized


class DatabaseSettings(BaseSettings):
    """Database connection settings (ADR-0001, ADR-0006).

    PostgreSQL is the primary database (ADR-0001). The connection URL is
    built from individual parts; the password is read only from the
    ``AIOS_DATABASE_PASSWORD`` environment variable and is never stored in
    configuration files or source code (ADR-0009 section 5.6).

    A complete connection string may override all parts through the
    ``AIOS_DATABASE_URL`` environment variable (highest priority).
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_DATABASE_", extra="ignore")

    driver: str = "postgresql+psycopg"
    host: str = "localhost"
    port: int = 5432
    name: str = "aios"
    user: str = "aios"
    password: str | None = None
    url: str | None = Field(default=None, validation_alias="AIOS_DATABASE_URL")

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy connection URL for this database.

        An explicit ``AIOS_DATABASE_URL`` overrides the parts-based URL.
        Otherwise the URL is built from the configured driver, user,
        password, host, port, and database name.
        """
        if self.url:
            return self.url
        credentials = f":{self.password}" if self.password else ""
        return f"{self.driver}://{self.user}{credentials}@{self.host}:{self.port}/{self.name}"


class IngestionSettings(BaseSettings):
    """Data ingestion configuration (AIOS-505, Phase 8).

    Controls batch size, rate limiting, and validation behavior for
    historical and batch ingestion operations. No secrets in configuration.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_INGESTION_", extra="ignore")

    batch_size: int = Field(default=100, ge=1, le=10000)
    rate_limit_ms: int = Field(default=0, ge=0)
    max_concurrent: int = Field(default=1, ge=1, le=10)
    quarantine_on_warning: bool = False
    freshness_max_age_days: int | None = Field(default=None, ge=1)
    default_exchange: str = "NASDAQ"


class SignalSettings(BaseSettings):
    """Signal Engine configuration (AIOS-605 section 10, Phase 9.2).

    Defines the directional decision thresholds and the technical/news
    component weights for the Signal Engine (ADR-0009 section 5.2).
    All values are tunable through the ``[signal]`` configuration section
    or environment variables with the ``AIOS_SIGNAL_`` prefix. The bullish
    bias is a single value in [0.0, 1.0]; scores at or above
    ``buy_threshold`` produce BUY, scores at or below ``sell_threshold``
    produce SELL, otherwise HOLD (AIOS-605 section 10). WAIT reports
    incomplete, conflicting, or low-confidence data.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_SIGNAL_", extra="ignore")

    technical_weight: float = Field(default=0.70, gt=0.0, lt=1.0)
    news_weight: float = Field(default=0.30, gt=0.0, lt=1.0)
    buy_threshold: float = Field(default=0.65, gt=0.0, lt=1.0)
    sell_threshold: float = Field(default=0.35, gt=0.0, lt=1.0)
    min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    min_news_items: int = Field(default=1, ge=0)
    require_news: bool = True


class DecisionSettings(BaseSettings):
    """Decision Engine scoring configuration (AIOS-406 sections 6-7, Phase 9.3).

    Defines the component weights, decision thresholds, and confidence
    methodology for the Decision Engine (ADR-0009 section 5.2).
    All values are tunable through the ``[decision]`` configuration section
    or environment variables with the ``AIOS_DECISION_`` prefix.

    Scoring components (normalized to [-1.0, +1.0]):
    - Signal: already combines Technical + News (Phase 9.2)
    - Fundamental: fundamental quality/growth/value
    - Market: market bias/environment
    - Risk/Portfolio: Hard Constraints, not scoring components (weight = 0.0)

    Hard Constraints (non-overridable, priority order):
    1. Shariah Gate: status != COMPLIANT → NO_TRADE
    2. Data/Analysis Gates: missing/invalid/insufficient → WAIT
    3. Risk Gate: approval_status = blocked → NO_TRADE
    4. Confidence Gate: confidence < min_confidence → WAIT
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_DECISION_", extra="ignore")

    # Component weights (sum need not equal 1.0; normalized internally)
    signal_weight: float = Field(default=0.60, ge=0.0)
    fundamental_weight: float = Field(default=0.20, ge=0.0)
    market_weight: float = Field(default=0.20, ge=0.0)
    # Technical/Risk/Portfolio weights are hardcoded to 0.0 per Phase 9.3 decision
    # (Technical included in Signal; Risk/Portfolio are Hard Constraints)

    # Decision thresholds on [-1.0, +1.0] score
    buy_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    sell_threshold: float = Field(default=0.65, ge=0.0, le=1.0)  # absolute value

    # Confidence methodology
    min_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    evidence_completeness_weight: float = Field(default=0.50, ge=0.0, le=1.0)
    component_agreement_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    data_quality_weight: float = Field(default=0.20, ge=0.0, le=1.0)


class PortfolioAllocationSettings(BaseSettings):
    """Portfolio Target Allocation configuration (AIOS-206 sections 6, 9, Phase 9.4).

    Defines the allocation scoring weights, risk adjustment parameters, and
    portfolio limits for the Portfolio Agent (ADR-0009 section 5.2).
    All values are tunable through the ``[portfolio]`` configuration section
    or environment variables with the ``AIOS_PORTFOLIO_`` prefix.

    Allocation Score Components (normalized to [0.0, 1.0]):
    - Decision Score: 50% (from DecisionEngine decision_score mapped to [0,1])
    - Signal Score: 25% (from SignalEngine score [0,1], already bullish-bias)
    - Risk Score: 25% (from RiskEngine risk_score [0,1] or derived)

    Hard Constraints (non-overridable, priority order):
    1. Shariah Gate: status != COMPLIANT → allocation = 0
    2. Risk Gate: approval_status = blocked → allocation = 0
    3. Decision Gate: decision = WAIT or NO_TRADE → allocation = 0
    4. Decision Gate: decision = HOLD → no new allocation (allocation = 0 for new positions)
    5. Risk Limits: allocation must not exceed RiskEngine max_position_percentage or max_sector_exposure

    Risk Adjustment:
    - Target weight scaled by confidence and risk_score
    - Max position weight and max portfolio exposure configurable
    - Allocation cannot exceed RiskEngine maximum_allowable_exposure
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_PORTFOLIO_", extra="ignore")

    # Allocation Score component weights (sum need not equal 1.0; normalized internally)
    decision_score_weight: float = Field(default=0.50, ge=0.0)
    signal_score_weight: float = Field(default=0.25, ge=0.0)
    risk_score_weight: float = Field(default=0.25, ge=0.0)

    # Portfolio limits
    max_position_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    max_portfolio_exposure: float = Field(default=1.0, ge=0.0, le=1.0)
    max_sector_exposure: float = Field(default=0.25, ge=0.0, le=1.0)

    # Risk adjustment
    confidence_scaling: bool = True
    risk_score_scaling: bool = True

    # Rebalancing
    rebalance_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    min_trade_size: float = Field(default=0.01, ge=0.0)


class BacktestSettings(BaseSettings):
    """Backtesting Framework configuration (AIOS-707, Phase 9.5).

    Defines the execution parameters, transaction costs, and risk management
    for the deterministic backtesting framework (ADR-0009 section 5.2).
    All values are tunable through the ``[backtest]`` configuration section
    or environment variables with the ``AIOS_BACKTEST_`` prefix.

    All transaction costs, slippage models, and fill policies are configurable
    to enable realistic execution simulation without live trading.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_BACKTEST_", extra="ignore")

    # Execution
    enabled: bool = True
    default_start_date: str = "2020-01-01"
    default_end_date: str = "2024-12-31"
    default_universe: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "JNJ", "V"])
    timeframe: str = "1d"

    # Capital
    initial_cash: float = Field(default=100_000.0, gt=0.0)
    currency: str = "USD"

    # Transaction Costs
    commission_bps: float = Field(default=10.0, ge=0.0)
    spread_bps: float = Field(default=5.0, ge=0.0)
    slippage_model: str = "fixed"
    slippage_bps: float = Field(default=2.0, ge=0.0)
    fill_policy: str = "exact"
    min_fill_fraction: float = Field(default=0.01, ge=0.0, le=1.0)

    # Risk Management
    max_position_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    max_sector_pct: float = Field(default=25.0, ge=0.0, le=100.0)

    # Portfolio Allocation
    max_position_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    max_portfolio_exposure: float = Field(default=1.0, ge=0.0, le=1.0)
    max_sector_exposure: float = Field(default=0.25, ge=0.0, le=1.0)
    confidence_scaling: bool = True
    risk_score_scaling: bool = True
    rebalance_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    min_trade_size: float = Field(default=0.01, ge=0.0)

    # Output
    save_equity_curve: bool = True
    save_fills: bool = True
    save_decisions: bool = True
    output_dir: str = "backtest_results/"

    # Performance
    parallel_symbols: bool = False
    checkpoint_interval: int = 100


# =============================================================================
# Phase 9.6 - Strategy Evaluation Configuration
# =============================================================================
# Phase 9.6 - Strategy Evaluation Configuration (nested settings)
# These must be defined before StrategyEvaluationSettings which uses them.
# =============================================================================

class StatisticalValidationSettings(BaseSettings):
    """Statistical validation configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_STAT_VALIDATION_", extra="ignore")

    # Minimum sample sizes
    min_trades_for_sharpe: int = Field(default=30, ge=1)
    min_trades_for_drawdown: int = Field(default=20, ge=1)

    # Confidence levels
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)

    # Stability thresholds
    sharpe_stability_threshold: float = Field(default=0.5, gt=0.0)
    return_stability_threshold: float = Field(default=0.5, gt=0.0)


class StrategyScoringSettings(BaseSettings):
    """Strategy scoring configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_STRATEGY_SCORING_", extra="ignore")

    # Component weights (must sum to 1.0)
    return_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    risk_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    consistency_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    robustness_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    oos_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    statistical_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    benchmark_weight: float = Field(default=0.05, ge=0.0, le=1.0)

    # Scoring thresholds
    excellent_threshold: float = Field(default=80.0, ge=0.0, le=100.0)
    good_threshold: float = Field(default=65.0, ge=0.0, le=100.0)
    acceptable_threshold: float = Field(default=50.0, ge=0.0, le=100.0)


class StrategyClassificationSettings(BaseSettings):
    """Strategy classification configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_STRATEGY_CLASSIFICATION_", extra="ignore")

    # Score thresholds for classification
    fail_threshold: float = Field(default=50.0, ge=0.0, le=100.0)
    weak_threshold: float = Field(default=65.0, ge=0.0, le=100.0)
    acceptable_threshold: float = Field(default=80.0, ge=0.0, le=100.0)
    # robust >= acceptable_threshold

    # Blocking conditions (override score-based classification)
    block_on_oos_failure: bool = True
    block_on_severe_drawdown: bool = True
    block_on_insufficient_sample: bool = True
    block_on_look_ahead: bool = True
    block_on_nondeterministic: bool = True
    max_drawdown_for_robust: float = Field(default=0.20, ge=0.0, le=1.0)


class BenchmarkSettings(BaseSettings):
    """Benchmark comparison configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_BENCHMARK_", extra="ignore")

    # Default benchmark symbols
    default_symbol: str = "SPY"
    buy_hold_symbol: str = "SPY"

    # Custom benchmark portfolio weights (symbol -> weight)
    custom_portfolio: dict[str, float] = Field(default_factory=dict)

    # Benchmark calculation settings
    include_costs: bool = False
    rebalance_frequency: str = "never"  # never, monthly, quarterly


class WalkForwardSettings(BaseSettings):
    """Walk-forward analysis configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_WALK_FORWARD_", extra="ignore")

    # Window sizes (in trading days)
    train_window_days: int = Field(default=252, ge=50)  # ~1 year
    test_window_days: int = Field(default=63, ge=10)    # ~3 months
    step_days: int = Field(default=63, ge=1)

    # Mode
    mode: str = "rolling"  # rolling, expanding

    # Minimum observations
    min_train_observations: int = Field(default=100, ge=30)
    min_test_observations: int = Field(default=20, ge=10)

    # Parameter optimization within training window
    optimize_parameters: bool = False
    parameter_grid: dict[str, list[float]] = Field(default_factory=dict)


class OutOfSampleSettings(BaseSettings):
    """Out-of-sample validation configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_OOS_", extra="ignore")

    # OOS period as fraction of total data
    oos_fraction: float = Field(default=0.3, gt=0.0, lt=1.0)

    # Minimum OOS period in days
    min_oos_days: int = Field(default=63, ge=10)

    # Strict validation
    strict_temporal_ordering: bool = True
    reject_on_overlap: bool = True


class SensitivitySettings(BaseSettings):
    """Parameter sensitivity analysis configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_SENSITIVITY_", extra="ignore")

    # Parameter ranges to test
    parameter_ranges: dict[str, list[float]] = Field(default_factory=dict)

    # Maximum combinations to test
    max_combinations: int = Field(default=100, ge=1)

    # Metric to optimize
    optimization_metric: str = "sharpe_ratio"

    # Deterministic execution
    deterministic: bool = True


class RobustnessSettings(BaseSettings):
    """Robustness testing configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_ROBUSTNESS_", extra="ignore")

    # Stress scenarios
    commission_multipliers: list[float] = Field(default=[1.0, 1.25, 1.5, 2.0])
    spread_multipliers: list[float] = Field(default=[1.0, 1.5, 2.0, 3.0])
    slippage_multipliers: list[float] = Field(default=[1.0, 1.5, 2.0, 3.0])
    execution_delays: list[int] = Field(default=[0, 1, 2, 3])
    min_fill_fractions: list[float] = Field(default=[0.01, 0.05, 0.1])

    # Degradation thresholds
    max_return_degradation: float = Field(default=0.5, gt=0.0)  # 50% max degradation
    max_drawdown_increase: float = Field(default=0.5, gt=0.0)


class MonteCarloSettings(BaseSettings):
    """Monte Carlo simulation configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_MONTE_CARLO_", extra="ignore")

    iterations: int = Field(default=10000, ge=100, le=100000)
    seed: int = Field(default=42, ge=0)
    confidence_levels: list[float] = Field(default=[0.05, 0.25, 0.5, 0.75, 0.95])
    drawdown_thresholds: list[float] = Field(default=[0.05, 0.10, 0.15, 0.20, 0.25])

    # Trade sequence shuffling
    shuffle_trades: bool = True
    preserve_chronology: bool = False


# =============================================================================
# Phase 9.6 - Strategy Evaluation Configuration
# =============================================================================

class StrategyEvaluationSettings(BaseSettings):
    """Strategy Evaluation configuration (Phase 9.6).

    Controls the behavior of strategy evaluation, benchmark comparison,
    and performance analysis.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_STRATEGY_EVAL_", extra="ignore")

    # Risk-free rate for Sharpe/Sortino (annualized)
    risk_free_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    # Minimum trades for statistical significance
    min_trades_for_significance: int = Field(default=30, ge=1)

    # Confidence level for intervals
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)

    # Enable/disable components
    enable_benchmark: bool = True
    enable_walk_forward: bool = True
    enable_sensitivity: bool = True
    enable_robustness: bool = True
    enable_monte_carlo: bool = True
    enable_regime_analysis: bool = True
    enable_statistical_validation: bool = True

    # Nested settings objects for each component
    statistical_validation: StatisticalValidationSettings = Field(default_factory=StatisticalValidationSettings)
    benchmark: BenchmarkSettings = Field(default_factory=BenchmarkSettings)
    walk_forward: WalkForwardSettings = Field(default_factory=WalkForwardSettings)
    oos: OutOfSampleSettings = Field(default_factory=OutOfSampleSettings)
    sensitivity: SensitivitySettings = Field(default_factory=SensitivitySettings)
    robustness: RobustnessSettings = Field(default_factory=RobustnessSettings)
    monte_carlo: MonteCarloSettings = Field(default_factory=MonteCarloSettings)
    strategy_scoring: StrategyScoringSettings = Field(default_factory=StrategyScoringSettings)
    strategy_classification: StrategyClassificationSettings = Field(default_factory=StrategyClassificationSettings)


class BenchmarkSettings(BaseSettings):
    """Benchmark comparison configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_BENCHMARK_", extra="ignore")

    # Default benchmark symbols
    default_symbol: str = "SPY"
    buy_hold_symbol: str = "SPY"

    # Custom benchmark portfolio weights (symbol -> weight)
    custom_portfolio: dict[str, float] = Field(default_factory=dict)

    # Benchmark calculation settings
    include_costs: bool = False
    rebalance_frequency: str = "never"  # never, monthly, quarterly


class WalkForwardSettings(BaseSettings):
    """Walk-forward analysis configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_WALK_FORWARD_", extra="ignore")

    # Window sizes (in trading days)
    train_window_days: int = Field(default=252, ge=50)  # ~1 year
    test_window_days: int = Field(default=63, ge=10)    # ~3 months
    step_days: int = Field(default=63, ge=1)

    # Mode
    mode: str = "rolling"  # rolling, expanding

    # Minimum observations
    min_train_observations: int = Field(default=100, ge=30)
    min_test_observations: int = Field(default=20, ge=10)

    # Parameter optimization within training window
    optimize_parameters: bool = False
    parameter_grid: dict[str, list[float]] = Field(default_factory=dict)


class OutOfSampleSettings(BaseSettings):
    """Out-of-sample validation configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_OOS_", extra="ignore")

    # OOS period as fraction of total data
    oos_fraction: float = Field(default=0.3, gt=0.0, lt=1.0)

    # Minimum OOS period in days
    min_oos_days: int = Field(default=63, ge=10)

    # Strict validation
    strict_temporal_ordering: bool = True
    reject_on_overlap: bool = True


class SensitivitySettings(BaseSettings):
    """Parameter sensitivity analysis configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_SENSITIVITY_", extra="ignore")

    # Parameter ranges to test
    parameter_ranges: dict[str, list[float]] = Field(default_factory=dict)

    # Maximum combinations to test
    max_combinations: int = Field(default=100, ge=1)

    # Metric to optimize
    optimization_metric: str = "sharpe_ratio"

    # Deterministic execution
    deterministic: bool = True


class RobustnessSettings(BaseSettings):
    """Robustness testing configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_ROBUSTNESS_", extra="ignore")

    # Stress scenarios
    commission_multipliers: list[float] = Field(default=[1.0, 1.25, 1.5, 2.0])
    spread_multipliers: list[float] = Field(default=[1.0, 1.5, 2.0, 3.0])
    slippage_multipliers: list[float] = Field(default=[1.0, 1.5, 2.0, 3.0])
    execution_delays: list[int] = Field(default=[0, 1, 2, 3])
    min_fill_fractions: list[float] = Field(default=[0.01, 0.05, 0.1])

    # Degradation thresholds
    max_return_degradation: float = Field(default=0.5, gt=0.0)  # 50% max degradation
    max_drawdown_increase: float = Field(default=0.5, gt=0.0)


class MonteCarloSettings(BaseSettings):
    """Monte Carlo simulation configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_MONTE_CARLO_", extra="ignore")

    iterations: int = Field(default=10000, ge=100, le=100000)
    seed: int = Field(default=42, ge=0)
    confidence_levels: list[float] = Field(default=[0.05, 0.25, 0.5, 0.75, 0.95])
    drawdown_thresholds: list[float] = Field(default=[0.05, 0.10, 0.15, 0.20, 0.25])

    # Trade sequence shuffling
    shuffle_trades: bool = True
    preserve_chronology: bool = False


class MonitoringSettings(BaseSettings):
    """Monitoring and alerting configuration (Phase 9.6)."""

    model_config = SettingsConfigDict(env_prefix="AIOS_MONITORING_", extra="ignore")

    # Prometheus metrics endpoint
    metrics_enabled: bool = True
    metrics_port: int = Field(default=9090, ge=1024, le=65535)
    metrics_path: str = "/metrics"

    # Health check
    health_check_enabled: bool = True
    health_check_port: int = Field(default=8080, ge=1024, le=65535)
    health_check_path: str = "/health"

    # Alerting
    alerting_enabled: bool = True
    alert_email_enabled: bool = False
    alert_email_recipients: list[str] = Field(default_factory=list)
    alert_slack_enabled: bool = False
    alert_slack_webhook: str | None = None

    # Alert thresholds
    alert_error_rate_threshold: float = Field(default=0.1, ge=0.0, le=1.0)  # 10% error rate
    alert_latency_p99_threshold_ms: int = Field(default=500, ge=100)  # 500ms P99
    alert_broker_disconnect_enabled: bool = True
    alert_shariah_violation_enabled: bool = True
    alert_gate_failure_enabled: bool = True

    # Evaluation window for the windowed alert rules (seconds)
    alert_window_seconds: int = Field(default=300, ge=10)

    # Performance thresholds
    ingestion_latency_p99_threshold_ms: int = Field(default=100, ge=50)
    decision_latency_p99_threshold_ms: int = Field(default=500, ge=100)

    # Metrics retention
    metrics_retention_hours: int = Field(default=168, ge=1)  # 1 week


class TradingSettings(BaseSettings):
    """Trading execution hardening configuration (Phase 9.6).

    These settings drive the order-path controls implemented in Phase 9.6:
    the pending-order timeout monitor, the bounded retry policy, and the
    market-session guard. All values are configuration-driven (ADR-0009) and
    overrideable through ``AIOS_TRADING_*`` environment variables.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_TRADING_", extra="ignore")

    # Pending order timeout (P0-3): a PENDING order older than this many
    # seconds is auto-cancelled and recorded as an ORDER_TIMEOUT event.
    order_timeout_enabled: bool = True
    pending_order_timeout_seconds: int = Field(default=300, ge=1)
    order_timeout_scan_interval_seconds: int = Field(default=30, ge=1)

    # Retry policy (P0-4): bounded exponential backoff for transient broker
    # operations. Validation, security, and gate failures are never retried.
    retry_enabled: bool = True
    retry_max_attempts: int = Field(default=3, ge=1)
    retry_base_delay_ms: int = Field(default=200, ge=1)
    retry_max_delay_ms: int = Field(default=2000, ge=1)
    retry_backoff_factor: float = Field(default=2.0, gt=1.0)

    # Market session guard (P0-5): order submission/execution is blocked while
    # the market is closed (weekend, holiday, or outside the session hours).
    market_session_enabled: bool = True
    market_timezone: str = "America/New_York"
    market_open: str = "09:30"
    market_close: str = "16:00"
    market_holidays: list[str] = Field(default_factory=list)  # ISO 8601 dates

    # Emergency stop (P0-2): kill switch enforced on the order submission path.
    emergency_stop_enabled: bool = True


# =============================================================================
# AppSettings
# =============================================================================

class AppSettings(BaseSettings):
    """Application settings resolved through pydantic-settings.

    Configuration source priority (ADR-0009 section 5.2):
        1. Environment variables (highest, prefix ``AIOS_``).
        2. Environment-specific configuration files.
        3. Default safe values (lowest).

    ``environment`` records the active runtime environment identified through
    the mandatory ``AIOS_ENVIRONMENT`` variable (ADR-0009 section 5.4) so
    configuration remains explicitly traceable to its environment.
    """

    model_config = SettingsConfigDict(env_prefix="AIOS_", extra="ignore")

    app_name: str = "aios"
    environment: Environment | None = None
    debug: bool = False
    database: DatabaseSettings = DatabaseSettings()
    logging: LoggingSettings = LoggingSettings()
    providers: "ProvidersConfig" = "ProvidersConfig()"
    ingestion: IngestionSettings = IngestionSettings()
    signal: SignalSettings = SignalSettings()
    decision: DecisionSettings = DecisionSettings()
    portfolio: PortfolioAllocationSettings = PortfolioAllocationSettings()
    backtest: BacktestSettings = BacktestSettings()
    strategy_evaluation: StrategyEvaluationSettings = StrategyEvaluationSettings()
    benchmark: BenchmarkSettings = BenchmarkSettings()
    walk_forward: WalkForwardSettings = WalkForwardSettings()
    oos: OutOfSampleSettings = OutOfSampleSettings()
    sensitivity: SensitivitySettings = SensitivitySettings()
    robustness: RobustnessSettings = RobustnessSettings()
    monte_carlo: MonteCarloSettings = MonteCarloSettings()
    statistical_validation: StatisticalValidationSettings = StatisticalValidationSettings()
    strategy_scoring: StrategyScoringSettings = StrategyScoringSettings()
    strategy_classification: StrategyClassificationSettings = StrategyClassificationSettings()
    monitoring: MonitoringSettings = MonitoringSettings()
    trading: TradingSettings = TradingSettings()
