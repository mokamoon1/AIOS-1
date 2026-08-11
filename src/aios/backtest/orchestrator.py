"""Backtest Orchestrator - Deterministic historical replay engine (Phase 9.5).

Coordinates the full backtest replay using the production engine pipeline:
Market -> Technical -> Fundamental -> Risk -> Signal -> Decision -> Portfolio -> PaperBroker

Key features:
- Deterministic timestamp iteration
- State isolation per backtest run
- Configuration snapshot at start
- Point-in-time data access via BacktestDataService
- Full audit trail and result persistence
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from aios.backtest.broker import BacktestPaperBroker
from aios.backtest.data import BacktestDataService
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
    create_backtest_engine_config,
)
from aios.brokers.models import PaperFill
from aios.config import load_settings
from aios.core import CoreEngine
from aios.data.models import DecisionAction, InvestmentDecision, Timeframe
from aios.data.services import DataService
from aios.engines.manager import EngineManager
from aios.engines.messages import EngineInput
from aios.engines.roster import create_engine
from aios.engines.types import EngineType
from aios.portfolio import PortfolioAllocationResult, PortfolioService
from aios.portfolio.models import TargetAllocation


class BacktestTimeIterator:
    """Deterministic time iterator for backtest replay.

    Iterates through timestamps at the configured timeframe frequency,
    ensuring deterministic replay across multiple runs.
    """

    def __init__(
        self,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> None:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware (UTC)")
        if start > end:
            raise ValueError("start must be <= end")

        self._start = start
        self._end = end
        self._timeframe = timeframe
        self._current = start

        # Parse timeframe to timedelta
        self._step = self._parse_timeframe(timeframe)

    @staticmethod
    def _parse_timeframe(timeframe: str) -> timedelta:
        """Parse timeframe string to timedelta."""
        timeframe = timeframe.lower().strip()
        if timeframe.endswith("m"):
            return timedelta(minutes=int(timeframe[:-1]))
        elif timeframe.endswith("h"):
            return timedelta(hours=int(timeframe[:-1]))
        elif timeframe.endswith("d"):
            return timedelta(days=int(timeframe[:-1]))
        elif timeframe.endswith("w"):
            return timedelta(weeks=int(timeframe[:-1]))
        elif timeframe.endswith("mo"):
            return timedelta(days=30 * int(timeframe[:-2]))
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    def __iter__(self):
        return self

    def __next__(self) -> datetime:
        if self._current > self._end:
            raise StopIteration
        current = self._current
        self._current += self._step
        return current

    def reset(self) -> None:
        """Reset iterator to start (for deterministic replay)."""
        self._current = self._start


class BacktestOrchestrator:
    """Orchestrates deterministic historical replay of the full engine pipeline.

    The orchestrator:
    1. Creates an isolated environment for each backtest run
    2. Snapshots configuration at start for deterministic replay
    3. Iterates through timestamps, driving the engine pipeline
    4. Manages portfolio state and equity curve
    5. Persists results and maintains full audit trail
    """

    def __init__(
        self,
        config: "BacktestConfig",
        data_service: "DataService",
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        # Runtime guard: Backtest must not run in live environments
        if config.environment in (Environment.PAPER, Environment.PRODUCTION):
            raise EngineValidationError(
                f"Backtest cannot run in {config.environment.value} environment. "
                f"Use TESTING or BACKTEST environment for backtesting."
            )
        
        self._config = config
        self._base_data_service = data_service
        self._logger = logger or logging.getLogger("aios.backtest.orchestrator")

        # Create isolated components for this backtest run
        self._run_id = uuid4()
        self._run = BacktestRun(
            id=self._run_id,
            config=config,
            status=BacktestStatus.RUNNING,
        )

        # Load settings snapshot for deterministic replay
        # CRITICAL: Snapshot ALL settings at backtest start for deterministic replay
        settings = load_settings()
        self._settings_snapshot = settings  # Full settings snapshot
        self._engine_config = create_backtest_engine_config(settings)
        
        # Snapshot portfolio settings for allocation
        self._portfolio_settings_snapshot = settings.portfolio
        
        # Snapshot backtest settings
        self._backtest_settings_snapshot = settings.backtest

        # Components (initialized in run())
        self._core_engine: "CoreEngine | None" = None
        self._engine_manager: "EngineManager | None" = None
        self._backtest_data_service: "BacktestDataService | None" = None
        self._paper_broker: "BacktestPaperBroker | None" = None
        self._portfolio_service: "PortfolioService | None" = None
        self._portfolio_agent = None

        # State
        self._equity_curve: list[EquityPoint] = []
        self._all_fills: list[Any] = []
        self._all_decisions: list[InvestmentDecision] = []
        self._all_allocations: list[PortfolioAllocationResult] = []

        # Performance tracking
        self._previous_equity: float = config.initial_cash
        self._peak_equity: float = config.initial_cash
        self._drawdown_start: datetime | None = None
        self._max_drawdown: float = 0.0
        self._max_drawdown_duration: int = 0
        self._current_drawdown_duration: int = 0

    async def run(self) -> BacktestResult:
        """Execute the full backtest replay."""
        self._logger.info(
            "Starting backtest run %s: %s to %s (%s)",
            self._run_id,
            self._config.start_date,
            self._config.end_date,
            self._config.timeframe,
        )

        try:
            await self._initialize_components()
            await self._run_replay()
            await self._finalize()

            self._run.status = BacktestStatus.COMPLETED
            self._run.completed_at = datetime.now(timezone.utc)
            self._run.result = self._build_result()

            self._logger.info("Backtest run %s completed successfully", self._run_id)
            return self._run.result

        except Exception as exc:
            self._logger.exception("Backtest run %s failed: %s", self._run_id, exc)
            self._run.status = BacktestStatus.FAILED
            self._run.completed_at = datetime.now(timezone.utc)
            self._run.error = str(exc)
            raise

    async def _initialize_components(self) -> None:
        """Initialize all backtest components with isolated state."""
        # Build isolated CoreEngine with backtest data service
        self._core_engine = CoreEngine(environment=self._config.environment)
        # Override database with in-memory for backtest
        from aios.database.base import Base
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        def _sqlite_engine():
            engine = create_engine(
                "sqlite://",
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
            Base.metadata.create_all(engine)
            return engine

        import aios.core.engine as core_module
        import aios.core.engine
        original_create_db_engine = aios.core.engine.create_db_engine
        aios.core.engine.create_db_engine = lambda url, **kwargs: _sqlite_engine()

        try:
            await self._core_engine.start()
        finally:
            aios.core.engine.create_db_engine = original_create_db_engine

        # Get managers
        self._engine_manager = self._core_engine.engine_manager
        base_data_service = self._core_engine._data_access

        # Create backtest data service with time ceiling
        start_dt = datetime.combine(self._config.start_date, datetime.min.time(), tzinfo=timezone.utc)
        self._backtest_data_service = BacktestDataService(base_data_service, start_dt)

        # Create backtest paper broker
        self._paper_broker = BacktestPaperBroker(
            broker_id="backtest",
            account_id="backtest-account",
            initial_cash=self._config.initial_cash,
            currency=self._config.currency,
            transaction_costs=self._config.transaction_costs,
        )
        self._paper_broker.set_current_time(start_dt)

        # Create portfolio service
        self._portfolio_service = PortfolioService(self._backtest_data_service)

        # Create portfolio agent with allocation settings (using SNAPSHOT)
        from aios.config.settings import PortfolioAllocationSettings
        allocation_settings = self._portfolio_settings_snapshot
        from aios.agents.roster import PortfolioAgent, create_agent
        from aios.agents.types import AgentType
        from aios.events import InMemoryEventBus

        bus = InMemoryEventBus()
        self._portfolio_agent = create_agent(
            AgentType.PORTFOLIO,
            bus=bus,
            portfolio_service=self._portfolio_service,
            allocation_settings=allocation_settings,
        )
        self._portfolio_agent.initialize()

        self._logger.info("Backtest components initialized")

    async def _run_replay(self) -> None:
        """Execute the main replay loop over all timestamps."""
        start_dt = datetime.combine(self._config.start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(self._config.end_date, datetime.max.time(), tzinfo=timezone.utc)

        time_iterator = BacktestTimeIterator(start_dt, end_dt, self._config.timeframe)

        # Pre-seed universe data if needed
        await self._seed_universe_data()

        step = 0
        for current_time in time_iterator:
            step += 1
            self._logger.debug("Backtest step %d: %s", step, current_time.isoformat())

            # Advance all time-sensitive components
            self._backtest_data_service.set_current_time(current_time)
            self._paper_broker.set_current_time(current_time)

            # Process each symbol in universe
            for symbol in self._config.universe:
                await self._process_symbol(symbol, current_time)

            # Record equity point after all symbols processed
            self._record_equity_point(current_time)

            # Log progress periodically
            if step % 100 == 0:
                self._logger.info("Backtest progress: step %d, time=%s", step, current_time.date())

    async def _seed_universe_data(self) -> None:
        """Seed database with historical data for all symbols in universe."""
        from aios.database.repositories import MarketRepository, ShariahRepository, CompanyRepository
        from aios.data.models import AssetType, Candle, ComplianceStatus, CompanyFundamentals, Security, MarketStatus, Timeframe, ShariahCompliance
        from datetime import date

        session_factory = self._core_engine.session_factory

        # Add securities
        market_repo = MarketRepository(session_factory)
        for symbol in self._config.universe:
            try:
                market_repo.add_security(Security(
                    symbol=symbol,
                    exchange="NASDAQ",
                    asset_type=AssetType.EQUITY,
                    currency="USD",
                    trading_session="regular",
                    timezone="America/New_York",
                    market_status=MarketStatus.OPEN,
                ))
            except Exception:
                pass  # Already exists

        # Add Shariah compliance (all compliant for backtest)
        shariah_repo = ShariahRepository(session_factory)
        for symbol in self._config.universe:
            try:
                shariah_repo.add_records([ShariahCompliance(
                    symbol=symbol,
                    company_name=symbol,
                    exchange="NASDAQ",
                    country="US",
                    asset_type=AssetType.EQUITY,
                    compliance_status=ComplianceStatus.COMPLIANT,
                    provider="backtest",
                    review_date=date(2020, 1, 1),
                    effective_date=date(2020, 1, 1),
                    expiration_date=date(2099, 12, 31),
                    screening_methodology="backtest",
                    screening_date=date(2020, 1, 1),
                )])
            except Exception:
                pass

        # Add mock fundamental data
        company_repo = CompanyRepository(session_factory)
        for symbol in self._config.universe:
            try:
                company_repo.add_fundamentals([CompanyFundamentals(
                    symbol=symbol,
                    sector="Technology",
                    industry="Software",
                    revenue=100_000_000_000.0,
                    net_income=20_000_000_000.0,
                    eps=5.0,
                    assets=300_000_000_000.0,
                    liabilities=100_000_000_000.0,
                    cash_flow=50_000_000_000.0,
                    equity=200_000_000_000.0,
                    report_date=date(2023, 12, 31),
                )])
            except Exception:
                pass

        # Seed market data - for backtest we need to populate candles
        # This would typically be done via ingestion pipeline
        # For now, we'll rely on the test infrastructure to populate data
        self._logger.info("Universe data seeded for %d symbols", len(self._config.universe))

    async def _process_symbol(self, symbol: str, current_time: datetime) -> None:
        """Process a single symbol through the full engine pipeline at current_time."""
        # Skip if not enough historical data yet
        try:
            candles = self._backtest_data_service.get_candles(
                symbol=symbol,
                timeframe=Timeframe.ONE_DAY,
                limit=250,
            )
            if len(candles) < 50:  # Need minimum data for indicators
                return
        except Exception:
            return

        # Build engine input
        engine_input = EngineInput(
            request_id=f"bt-{symbol}-{current_time.isoformat()}",
            payload={
                "symbol": symbol,
                "timeframe": self._config.timeframe,
                "limit": 250,
                "max_position_percentage": self._config.max_position_pct,
                "max_sector_exposure": self._config.max_sector_pct,
                "portfolio_value": self._get_current_equity(),
                "requested_position_percentage": 5.0,  # Default position size request
            },
        )

        # Run the full engine pipeline
        try:
            results = await self._engine_manager.run_pipeline(list(EngineType), engine_input)
        except Exception as exc:
            self._logger.warning("Pipeline failed for %s at %s: %s", symbol, current_time, exc)
            return

        # Extract decision
        decision_output = results.get(EngineType.DECISION)
        if decision_output is None:
            return

        decision_data = decision_output.output
        decision = decision_data.get("decision")

        # Store decision for audit trail
        if hasattr(decision_output, 'engine_id'):
            decision_record = InvestmentDecision(
                symbol=symbol,
                decision=DecisionAction(decision),
                reason=decision_data.get("reason", ""),
                confidence=decision_data.get("confidence", 0.0),
                risk_score=decision_data.get("risk_score"),
                timestamp=current_time,
                supporting_data=decision_data,
            )
            self._all_decisions.append(decision_record)

            # Persist decision
            try:
                self._backtest_data_service.store_decisions([decision_record])
            except Exception:
                pass

        # Process portfolio allocation if decision is actionable
        if decision in ("buy", "sell"):
            await self._process_allocation(symbol, decision, decision_data, current_time)

    async def _process_allocation(
        self,
        symbol: str,
        decision: str,
        decision_data: dict,
        current_time: datetime,
    ) -> None:
        """Process portfolio allocation for actionable decisions."""
        # Get signal and risk outputs for allocation scoring
        signal_output = None
        risk_output = None

        # We need to get these from the engine manager results
        # For now, we'll extract from decision_data if available

        # Build allocation context
        context_payload = {
            "symbols": [symbol],
            "decision_outputs": {symbol: decision_data},
            "signal_outputs": {symbol: {}},  # Would come from SignalEngine
            "risk_outputs": {symbol: {}},  # Would come from RiskEngine
        }

        from aios.agents.messages import AgentContext
        context = AgentContext(
            request_id=f"alloc-{symbol}-{current_time.isoformat()}",
            payload=context_payload,
        )

        try:
            result = await self._portfolio_agent.execute(context)
            allocation_result = result.output.get("recommended_allocation")

            if allocation_result:
                # Create PortfolioAllocationResult
                alloc_record = PortfolioAllocationResult(
                    generated_at=current_time,
                    total_portfolio_value=self._get_current_equity(),
                    target_allocations=[
                        TargetAllocation(
                            symbol=symbol,
                            exchange="NASDAQ",
                            target_weight=allocation_result.get("target_weight", 0.0),
                            target_value=allocation_result.get("target_value", 0.0),
                            current_weight=0.0,
                            current_value=0.0,
                            action=allocation_result.get("action", "hold"),
                            allocation_score=allocation_result.get("allocation_score", 0.0),
                            confidence=allocation_result.get("confidence", 0.0),
                            risk_adjustment=allocation_result.get("risk_adjustment", 1.0),
                            hard_constraints_triggered=allocation_result.get("hard_constraints_triggered", []),
                            reasons=allocation_result.get("reasons", []),
                        )
                    ],
                    rebalance_suggestion=None,
                    hard_constraints_triggered=[],
                    explanation=f"Backtest allocation for {symbol} at {current_time}",
                )
                self._all_allocations.append(alloc_record)

                # Execute trade via paper broker
                await self._execute_trade(symbol, decision, allocation_result, current_time)

        except Exception as exc:
            self._logger.warning("Allocation failed for %s at %s: %s", symbol, current_time, exc)

    async def _execute_trade(
        self,
        symbol: str,
        decision: str,
        allocation_result: dict,
        current_time: datetime,
    ) -> None:
        """Execute trade via paper broker."""
        target_weight = allocation_result.get("target_weight", 0.0)
        if target_weight <= 0:
            return

        equity = self._get_current_equity()
        target_value = equity * target_weight

        # Get current price
        candles = self._backtest_data_service.get_candles(
            symbol=symbol,
            timeframe=Timeframe.ONE_DAY,
            limit=1,
        )
        if not candles:
            return
        price = candles[-1].close

        quantity = target_value / price if price > 0 else 0
        if quantity <= 0:
            return

        from aios.agents.permissions import Role
        side = "buy" if decision == "buy" else "sell"

        # Submit order
        try:
            order = self._paper_broker.submit_order(
                PaperOrder(
                    order_id="",  # Will be generated
                    broker_id="backtest",
                    symbol=symbol,
                    exchange="NASDAQ",
                    side=OrderSide.BUY if decision == "buy" else OrderSide.SELL,
                    quantity=quantity,
                    price=price,
                )
            )
            # Fill at current price (with transaction costs applied internally)
            filled, fill = self._paper_broker.fill_order(order.order_id, price=price)
            self._all_fills.append(fill)
        except Exception as exc:
            self._logger.warning("Trade execution failed for %s: %s", symbol, exc)

    def _record_equity_point(self, current_time: datetime) -> None:
        """Record equity curve point at current timestamp."""
        equity = self._get_current_equity()
        cash = self._paper_broker._cash if self._paper_broker else self._config.initial_cash
        market_value = equity - cash

        # Calculate daily return
        daily_return = 0.0
        if self._equity_curve:
            daily_return = (equity - self._equity_curve[-1].equity) / self._equity_curve[-1].equity

        cumulative_return = (equity - self._config.initial_cash) / self._config.initial_cash

        point = EquityPoint(
            timestamp=current_time,
            equity=equity,
            cash=cash,
            market_value=market_value,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
        )
        self._equity_curve.append(point)

        # Update drawdown tracking
        if equity > self._peak_equity:
            self._peak_equity = equity
            self._current_drawdown_duration = 0
        else:
            drawdown = (self._peak_equity - equity) / self._peak_equity
            if drawdown > self._max_drawdown:
                self._max_drawdown = drawdown
            self._current_drawdown_duration += 1
            if self._current_drawdown_duration > self._max_drawdown_duration:
                self._max_drawdown_duration = self._current_drawdown_duration

        self._previous_equity = equity

    def _get_current_equity(self) -> float:
        if self._paper_broker:
            status = self._paper_broker.get_portfolio_status()
            return status.equity
        return self._config.initial_cash

    async def _finalize(self) -> None:
        """Finalize backtest and compute performance metrics."""
        from aios.backtest.calculator import PerformanceCalculator

        calculator = PerformanceCalculator()
        performance = calculator.compute(
            equity_curve=self._equity_curve,
            fills=self._all_fills,
            initial_cash=self._config.initial_cash,
        )

        risk_metrics = calculator.compute_risk_metrics(
            equity_curve=self._equity_curve,
            fills=self._all_fills,
        )

        # Store engine metrics
        engine_metrics = {}
        if self._engine_manager:
            for engine in self._engine_manager.list_engines():
                engine_metrics[engine.engine_type.value] = engine.metrics()

        self._run.result = BacktestResult(
            config=self._config,
            started_at=self._run.started_at,
            completed_at=datetime.now(timezone.utc),
            equity_curve=self._equity_curve,
            fills=self._all_fills,
            performance=performance,
            risk_metrics=risk_metrics,
            decisions=self._all_decisions,
            allocations=self._all_allocations,
            engine_metrics=engine_metrics,
        )

        # Persist backtest run
        await self._persist_run()

    async def _persist_run(self) -> None:
        """Persist backtest run and results to database."""
        if self._core_engine and self._core_engine.session_factory:
            from aios.database.repositories import BacktestRepository
            repo = BacktestRepository(self._core_engine.session_factory)
            repo.add_run(self._run)

    def _build_result(self) -> BacktestResult:
        return self._run.result