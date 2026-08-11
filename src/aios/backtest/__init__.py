"""AIOS Backtesting Framework (AIOS-707, Phase 9.5).

Deterministic historical replay framework that reuses the production engine pipeline:
Market -> Technical -> Fundamental -> Risk -> Signal -> Decision -> Portfolio -> PaperBroker

Key principles:
- Deterministic replay using point-in-time data access
- No look-ahead bias: all data queries bounded by current backtest timestamp
- Reuses exact production engine pipeline
- No live trading paths
- Full explainability and audit trail
"""

from __future__ import annotations

from aios.backtest.models import (
    BacktestConfig,
    BacktestEngineConfig,
    BacktestResult,
    BacktestRun,
    BacktestStatus,
    EquityPoint,
    PerformanceSnapshot,
    RiskMetrics,
    TransactionCostConfig,
    FillPolicy,
    SlippageModel,
    FillPolicy,
    create_backtest_engine_config,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngineConfig",
    "BacktestResult",
    "BacktestRun",
    "BacktestStatus",
    "EquityPoint",
    "PerformanceSnapshot",
    "RiskMetrics",
    "TransactionCostConfig",
    "FillPolicy",
    "SlippageModel",
    "create_backtest_engine_config",
]