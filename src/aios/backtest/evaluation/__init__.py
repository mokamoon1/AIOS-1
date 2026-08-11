"""AIOS Backtesting Framework - Strategy Evaluation & Analytics (Phase 9.6).

Provides comprehensive strategy validation and backtest analytics:
- Strategy Evaluation Engine
- Benchmark Comparison (Buy & Hold, Custom Benchmarks)
- Walk-Forward Analysis
- Out-of-Sample Testing
- Parameter Sensitivity Analysis
- Robustness Testing
- Market Regime Analysis
- Monte Carlo / Trade Sequence Analysis
- Statistical Validation
- Strategy Scoring & Classification
- Backtest Comparison
- Report Generation
"""

from __future__ import annotations

from aios.backtest.evaluation.strategy_evaluator import StrategyEvaluator, StrategyEvaluationResult
from aios.backtest.evaluation.benchmark import BenchmarkEngine, BenchmarkResult, BuyHoldCalculator
from aios.backtest.evaluation.walk_forward import WalkForwardAnalyzer, WalkForwardResult
from aios.backtest.evaluation.oos import OutOfSampleValidator, OOSValidationResult
from aios.backtest.evaluation.sensitivity import SensitivityAnalyzer, SensitivityResult
from aios.backtest.evaluation.robustness import RobustnessAnalyzer, RobustnessResult
from aios.backtest.evaluation.regime import MarketRegimeAnalyzer
from aios.backtest.evaluation.monte_carlo import MonteCarloEngine, MonteCarloResult
from aios.backtest.evaluation.validation import StatisticalValidator, StatisticalValidationResult
from aios.backtest.evaluation.scoring import StrategyScorer, StrategyScore
from aios.backtest.evaluation.classification import StrategyClassifier, StrategyClassification
from aios.backtest.evaluation.comparison import BacktestComparator, ComparisonResult
from aios.backtest.evaluation.report import ReportGenerator

__all__ = [
    # Core Evaluation
    "StrategyEvaluator",
    "StrategyEvaluationResult",
    # Benchmark & Buy & Hold
    "BenchmarkEngine",
    "BenchmarkResult",
    "BuyHoldCalculator",
    # Walk-Forward & OOS
    "WalkForwardAnalyzer",
    "WalkForwardResult",
    "OutOfSampleValidator",
    "OOSValidationResult",
    # Analysis
    "SensitivityAnalyzer",
    "SensitivityResult",
    "RobustnessAnalyzer",
    "RobustnessResult",
    "MarketRegimeAnalyzer",
    # Monte Carlo & Validation
    "MonteCarloEngine",
    "MonteCarloResult",
    "StatisticalValidator",
    "StatisticalValidationResult",
    # Scoring & Classification
    "StrategyScorer",
    "StrategyScore",
    "StrategyClassifier",
    "StrategyClassification",
    # Comparison
    "BacktestComparator",
    "ComparisonResult",
    # Reporting
    "ReportGenerator",
]