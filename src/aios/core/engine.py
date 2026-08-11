"""Core Engine bootstrap (AIOS-104 section 4).

The Core Engine owns system startup and shutdown. The approved startup
sequence (AIOS-104 section 4) is:

1. Load Configuration (Configuration Manager, AIOS-104 section 5.1)
2. Initialize Database (AIOS-104 section 5.2)
3. Initialize Event Bus
4. Load AI Agents (Agent Manager, AIOS-104 section 5.3)
5. Connect Data Providers

Engines are loaded with the Agent Manager so that the Decision Engine can
consume agent outputs (AIOS-104 section 5.3, AIOS-605 section 11). Phase 1
registers no concrete providers and opens no live database connection: the
provider interface and the database layer are wired but left inert so the
bootstrap runs without external services (AIOS-603 section 6).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from aios.analysis.news_engine import NewsEngine
from aios.agents import AgentManager
from aios.agents.roster import AgentType, PortfolioAgent, create_agent
from aios.agents.types import AgentState
from aios.brokers import BrokerService, PaperBroker, PaperOrderCoordinator
from aios.brokers.guards import (
    EmergencyStopGuard,
    GuardChain,
    MarketSessionGuardAdapter,
)
from aios.brokers.market_session import MarketSessionGuard
from aios.brokers.retry import RetryPolicy
from aios.brokers.timeout import PendingOrderTimeoutMonitor
from aios.config import AppSettings, Environment, get_environment, load_settings
from aios.core.exceptions import CoreBootstrapError, CoreStateError
from aios.data.ingestion import IngestionConfig, IngestionService
from aios.data.pipeline import DataPipeline
from aios.data.services import DataService
from aios.data.validation import DataValidator
from aios.database import create_db_engine, create_session_factory
from aios.database.repositories import (
    BrokerAccountRepository,
    CompanyRepository,
    DecisionRepository,
    MarketRepository,
    NewsRepository,
    PaperFillRepository,
    PaperOrderRepository,
    PaperPositionRepository,
    PortfolioRepository,
    ShariahRepository,
)
from aios.engines import EngineManager
from aios.engines.roster import EngineType, create_engine
from aios.engines.types import EngineState
from aios.events import Event, EventPriority, InMemoryEventBus
from aios.logging import setup_audit_handler, setup_logging
from aios.monitoring import (
    create_alert_manager,
    create_emergency_stop_manager,
    update_system_metrics,
)
from aios.monitoring.event_log import (
    EVENT_BROKER_CONNECTED,
    EVENT_BROKER_DISCONNECTED,
    EventLog,
)
from aios.portfolio import PortfolioService
from aios.providers import ProviderFactory, ProviderManager


class CoreState(str, Enum):
    """Lifecycle states of the Core Engine (AIOS-104 sections 4 and 7)."""

    UNINITIALIZED = "uninitialized"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    SHUTDOWN = "shutdown"


class CoreEngine:
    """Coordinates the platform startup/shutdown sequence (AIOS-104 section 4).

    Startup stages run in the documented order; any failure is recorded,
    already-initialized components are rolled back, and the Core Engine is
    marked ``FAILED`` (AIOS-104 sections 4 and 7).
    """

    def __init__(
        self,
        *,
        environment: Environment | None = None,
        config_dir: Path | None = None,
        logger: logging.Logger | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._environment = environment
        self._config_dir = config_dir
        self._logger = logger or logging.getLogger("aios.core.engine")
        self._clock = clock
        self._settings: AppSettings | None = None
        self._active_environment: Environment | None = None
        self._root_logger = None
        self._audit_logger = None
        self._db_engine = None
        self._session_factory = None
        self._bus: InMemoryEventBus | None = None
        self._agent_manager: AgentManager | None = None
        self._engine_manager: EngineManager | None = None
        self._provider_manager: ProviderManager | None = None
        self._ingestion_service: IngestionService | None = None
        self._data_access: DataService | None = None
        self._broker_service: BrokerService | None = None
        self._paper_coordinator: PaperOrderCoordinator | None = None
        self._metrics_server: Any = None
        self._metrics_task: Any = None
        self._alert_manager: Any = None
        self._event_log: EventLog | None = None
        self._stop_manager: Any = None
        self._market_session_guard: MarketSessionGuard | None = None
        self._retry_policy: RetryPolicy | None = None
        self._order_timeout_monitor: PendingOrderTimeoutMonitor | None = None
        self._order_timeout_task: Any = None
        self._start_time: float = time.time()
        self._state = CoreState.UNINITIALIZED

    @property
    def state(self) -> CoreState:
        """Current Core Engine lifecycle state."""
        return self._state

    @property
    def settings(self) -> AppSettings | None:
        """Loaded application settings (None until startup)."""
        return self._settings

    @property
    def bus(self) -> InMemoryEventBus | None:
        """Initialized Event Bus (None until startup)."""
        return self._bus

    @property
    def agent_manager(self) -> AgentManager | None:
        """Agent Manager loaded at startup (AIOS-104 section 5.3)."""
        return self._agent_manager

    @property
    def engine_manager(self) -> EngineManager | None:
        """Engine Manager loaded at startup (AIOS-605 section 3)."""
        return self._engine_manager

    @property
    def provider_manager(self) -> ProviderManager | None:
        """Provider Manager (AIOS-104 section 5.2)."""
        return self._provider_manager

    @property
    def ingestion_service(self) -> IngestionService | None:
        """Ingestion Service for data ingestion operations (Phase 8)."""
        return self._ingestion_service

    @property
    def broker_service(self) -> BrokerService | None:
        """Authorized Paper Broker facade (PAPER environment only; None otherwise).

        Live brokers are never wired: Paper Trading is the only execution
        mode (AIOS-101 section 4.6, AIOS-603 section 11).
        """
        return self._broker_service

    @property
    def paper_coordinator(self) -> PaperOrderCoordinator | None:
        """Decision-to-broker router (PAPER environment only; None otherwise)."""
        return self._paper_coordinator

    @property
    def session_factory(self) -> Any:
        """Database session factory (None until startup)."""
        return self._session_factory

    @property
    def event_log(self) -> EventLog | None:
        """Operational event log shared by the alerting and audit paths."""
        return self._event_log

    @property
    def stop_manager(self) -> Any:
        """Emergency stop / kill switch manager (Phase 9.6)."""
        return self._stop_manager

    @property
    def market_session_guard(self) -> MarketSessionGuard | None:
        """Market session guard wired on the order path (Phase 9.6)."""
        return self._market_session_guard

    @property
    def order_timeout_monitor(self) -> PendingOrderTimeoutMonitor | None:
        """Pending-order timeout monitor (Phase 9.6)."""
        return self._order_timeout_monitor

    async def start(self) -> None:
        """Run the documented startup sequence (AIOS-104 section 4)."""
        if self._state not in (CoreState.UNINITIALIZED, CoreState.FAILED):
            raise CoreStateError(f"Cannot start Core Engine from state {self._state.value!r}")
        self._state = CoreState.STARTING
        self._logger.info("Core Engine starting")
        try:
            await self._start_configuration()
            await self._start_logging()
            await self._start_database()
            await self._start_event_bus()
            await self._start_agents()
            await self._start_engines()
            self._start_trading_controls()
            await self._start_broker()
            await self._start_providers()
            await self._start_ingestion()
            await self._start_metrics()
            await self._start_alerting()
            self._start_order_timeout_monitor()
            self._validate_ready()
            self._state = CoreState.READY
            await self._publish_system_event("SYSTEM_READY")
            self._logger.info("Core Engine ready")
        except Exception as exc:
            self._state = CoreState.FAILED
            self._logger.exception("Core Engine startup failed: %s", exc)
            await self._rollback()
            raise CoreBootstrapError(f"Core Engine startup failed: {exc}") from exc

    async def shutdown(self) -> None:
        """Shut the platform down in reverse order of startup (AIOS-104 section 4)."""
        if self._state in (CoreState.UNINITIALIZED, CoreState.SHUTDOWN):
            return
        self._logger.info("Core Engine shutting down")
        try:
            await self._publish_system_event("SYSTEM_SHUTDOWN")
        finally:
            await self._teardown_components()
            self._state = CoreState.SHUTDOWN
            self._logger.info("Core Engine shut down")

    def is_ready(self) -> bool:
        """Return whether the Core Engine reached the READY state."""
        return self._state is CoreState.READY

    def status(self) -> dict[str, Any]:
        """Return a component status map for health reporting (AIOS-104 section 5.2)."""
        agents = self._agent_manager.list_agents() if self._agent_manager else []
        engines = self._engine_manager.list_engines() if self._engine_manager else []
        return {
            "state": self._state.value,
            "environment": (
                self._active_environment.value if self._active_environment is not None else None
            ),
            "components": {
                "configuration": self._settings is not None,
                "logging": self._root_logger is not None,
                "database": self._db_engine is not None,
                "event_bus": self._bus is not None,
                "broker": self._broker_service is not None,
                "agents": {
                    "loaded": len(agents),
                    "ready": sum(1 for agent in agents if agent.state is AgentState.INITIALIZED),
                },
                "engines": {
                    "loaded": len(engines),
                    "ready": sum(
                        1 for engine in engines if engine.state is EngineState.INITIALIZED
                    ),
                },
                "providers": (self._provider_manager.status() if self._provider_manager else {}),
                "ingestion": (
                    self._ingestion_service.get_adapter_status()
                    if self._ingestion_service
                    else {}
                ),
            },
        }

    async def _start_metrics(self) -> None:
        """Start Prometheus metrics server (Phase 9.6)."""
        settings = self._settings
        if settings is None:
            return
        
        monitoring = settings.monitoring
        if not monitoring.metrics_enabled:
            self._logger.info("Metrics server disabled by configuration")
            return
        
        try:
            from aios.monitoring.metrics import metrics_endpoint
            from starlette.applications import Starlette
            from starlette.routing import Route
            import uvicorn
            
            app = Starlette(
                routes=[
                    Route(monitoring.metrics_path, metrics_endpoint, methods=["GET"]),
                ]
            )
            
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=monitoring.metrics_port,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config)

            # Start server in background task (guarded so a bind failure or
            # uvicorn startup sys.exit does not take down the process).
            self._metrics_server = server
            self._metrics_task = asyncio.create_task(
                self._run_metrics_server(server)
            )

            self._logger.info("Metrics server started on port %d", monitoring.metrics_port)

        except Exception as exc:
            self._logger.warning("Failed to start metrics server: %s", exc)

    async def _run_metrics_server(self, server: Any) -> None:
        """Serve the Prometheus endpoint without letting failures escape."""
        try:
            await server.serve()
        except SystemExit as exc:
            # uvicorn calls sys.exit(STARTUP_FAILURE) when startup fails
            # (e.g. metrics port already in use); treat as best-effort.
            self._logger.warning("Metrics server failed to start: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Metrics server error: %s", exc)

    async def _stop_metrics(self) -> None:
        """Stop the Prometheus metrics server and free its port."""
        if self._metrics_server is None:
            return
        try:
            self._metrics_server.should_exit = True
        except Exception:  # noqa: BLE001
            pass
        task = self._metrics_task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            self._metrics_task = None
        self._metrics_server = None

    async def _start_alerting(self) -> None:
        """Start alert manager (Phase 9.6)."""
        settings = self._settings
        if settings is None:
            return

        monitoring = settings.monitoring
        if not monitoring.alerting_enabled:
            self._logger.info("Alerting disabled by configuration")
            return

        try:
            self._alert_manager = create_alert_manager(
                settings,
                self._logger,
                event_log=self._event_log,
            )
            await self._alert_manager.start(bus=self._bus)
            self._logger.info("Alert manager started")
        except Exception as exc:
            self._logger.warning("Failed to start alert manager: %s", exc)

    def _start_order_timeout_monitor(self) -> None:
        """Start the periodic pending-order timeout scanner (Phase 9.6, P0-3)."""
        settings = self._settings
        broker_service = self._broker_service
        if settings is None or broker_service is None:
            return
        trading = settings.trading
        if not trading.order_timeout_enabled:
            self._logger.info("Order timeout monitor disabled by configuration")
            return
        self._order_timeout_monitor = PendingOrderTimeoutMonitor(
            broker_service,
            timeout_seconds=int(trading.pending_order_timeout_seconds),
            event_log=self._event_log,
        )
        interval = float(trading.order_timeout_scan_interval_seconds)

        async def _scan_loop() -> None:
            while True:
                try:
                    orders = broker_service.list_orders()
                    self._order_timeout_monitor.cancel_expired(orders)
                except Exception as exc:  # noqa: BLE001 - monitor must not die
                    self._logger.warning("Order timeout scan failed: %s", exc)
                await asyncio.sleep(interval)

        self._order_timeout_task = asyncio.create_task(_scan_loop())
        self._logger.info(
            "Order timeout monitor started (timeout=%ds, scan every %ds)",
            trading.pending_order_timeout_seconds,
            interval,
        )

    async def _start_configuration(self) -> None:
        active = self._environment
        if active is None:
            active = get_environment()
        self._active_environment = active
        self._settings = load_settings(active, self._config_dir)
        self._logger.info("Configuration loaded for environment %s", active.value)

    async def _start_logging(self) -> None:
        settings = self._settings
        if settings is None:
            raise CoreBootstrapError("Configuration must be loaded before logging")
        self._root_logger = setup_logging(settings.logging)
        self._audit_logger = setup_audit_handler(self._root_logger)
        self._logger.info("Logging initialized")

    async def _start_database(self) -> None:
        settings = self._settings
        if settings is None:
            raise CoreBootstrapError("Configuration must be loaded before database")
        self._db_engine = create_db_engine(settings.database.database_url)
        self._session_factory = create_session_factory(self._db_engine)
        self._logger.info("Database layer initialized")

    async def _start_event_bus(self) -> None:
        self._bus = InMemoryEventBus()
        self._logger.info("Event Bus initialized")

    async def _start_agents(self) -> None:
        manager = AgentManager()
        for agent_type in AgentType:
            manager.register(create_agent(agent_type, bus=self._bus))
        self._agent_manager = manager
        self._logger.info("Agent Manager loaded %d agents", len(manager.list_agents()))

    async def _start_engines(self) -> None:
        manager = EngineManager()
        data_access = self._build_data_access()
        self._data_access = data_access
        # The Signal Engine is registered before providers connect (AIOS-104
        # section 4); its News Intelligence Engine is built and attached in
        # ``_start_ingestion`` once the connected News provider adapter is
        # available (AIOS-605 section 10).
        for engine_type in EngineType:
            manager.register(
                create_engine(
                    engine_type,
                    bus=self._bus,
                    data_access=data_access,
                )
            )
        self._engine_manager = manager
        self._wire_portfolio_agent(data_access)
        self._logger.info("Engine Manager loaded %d engines", len(manager.list_engines()))

    def _start_trading_controls(self) -> None:
        """Build the Phase 9.6 execution controls (kill switch, market session, retry).

        The controls are configuration-driven (``[trading]``, ADR-0009) and
        shared through the process-wide operational ``EventLog`` so their audit
        events reach the alerting rules.
        """
        settings = self._settings
        if settings is None:
            return
        trading = settings.trading
        self._event_log = EventLog()
        self._stop_manager = create_emergency_stop_manager(settings, event_log=self._event_log)
        self._market_session_guard = MarketSessionGuard.from_settings(trading, now_fn=self._clock)
        self._retry_policy = RetryPolicy.from_settings(trading)
        self._logger.info(
            "Trading controls built: stop=%s market_session=%s retry=%d attempt(s)",
            self._stop_manager.is_stopped,
            self._market_session_guard.enabled,
            self._retry_policy.max_attempts,
        )

    async def _start_broker(self) -> None:
        """Wire the authorized Paper Broker (PAPER environment only, AIOS-603 section 11).

        The Paper Broker is constructed only in the Paper environment: its
        order book, fills, positions, and account are persisted through the
        Data Layer facade (AIOS-606 section 1), and approved decisions are
        routed through the coordinator under ``SUBMIT_PAPER_ORDERS``
        authorization (AIOS-408 section 8, AIOS-406 section 13). The Phase 9.6
        guards (kill switch, market session) and retry policy are attached to
        the authorized facade. No live broker and no production execution are
        ever wired (AIOS-208 section 8).
        """
        settings = self._settings
        data_access = self._data_access
        environment = self._environment or get_environment()
        if settings is None or data_access is None or environment is not Environment.PAPER:
            self._logger.info(
                "Paper Broker not wired (active environment: %s)",
                environment.value,
            )
            return
        paper_broker = PaperBroker("paper", "paper-account")
        # Restore account state from database if available (AIOS-407 section 4.3)
        try:
            account = data_access.get_broker_account("paper")
            paper_broker.restore_account(account)
        except Exception:
            # No persisted account; broker starts with default initial_cash
            self._logger.info("No persisted broker account found; starting with default initial cash")

        guard_chain = GuardChain()
        if self._stop_manager is not None:
            guard_chain.add_guard(EmergencyStopGuard(self._stop_manager))
        if self._market_session_guard is not None:
            guard_chain.add_guard(MarketSessionGuardAdapter(self._market_session_guard))

        self._broker_service = BrokerService(
            paper_broker,
            store=data_access,
            guards=guard_chain,
            retry_policy=self._retry_policy,
            event_log=self._event_log,
        )
        self._paper_coordinator = PaperOrderCoordinator(self._broker_service, data_access)
        if self._event_log is not None:
            self._event_log.record(
                EVENT_BROKER_CONNECTED,
                "core.engine",
                payload={"source": "core.engine", "broker_id": "paper"},
            )
        self._logger.info("Paper Broker wired for environment %s", environment.value)

    def _wire_portfolio_agent(self, data_access: DataService | None) -> None:
        """Attach the Portfolio Service to the Portfolio Agent (AIOS-603 section 10).

        The service consumes the current-holdings view through the Data
        Layer facade, so the Portfolio Agent never touches the database
        directly (AIOS-501 section 2, AIOS-606 section 1).
        """
        if data_access is None or self._agent_manager is None:
            return
        portfolio_service = PortfolioService(data_access)
        for agent in self._agent_manager.get_by_type(AgentType.PORTFOLIO):
            if isinstance(agent, PortfolioAgent):
                agent.attach_portfolio_service(portfolio_service)

    def _build_data_access(self) -> DataService | None:
        """Build the Data Layer facade engines consume (AIOS-501 section 2).

        The DataService routes reads to the Database Layer repositories
        created from the startup session factory, so analysis engines never
        touch providers or the database directly (AIOS-605 section 13).
        """
        if self._session_factory is None:
            return None
        return DataService(
            DataPipeline(DataValidator()),
            market_repository=MarketRepository(self._session_factory),
            shariah_repository=ShariahRepository(self._session_factory),
            fundamental_repository=CompanyRepository(self._session_factory),
            portfolio_repository=PortfolioRepository(self._session_factory),
            decision_repository=DecisionRepository(self._session_factory),
            paper_order_repository=PaperOrderRepository(self._session_factory),
            paper_fill_repository=PaperFillRepository(self._session_factory),
            paper_position_repository=PaperPositionRepository(self._session_factory),
            broker_account_repository=BrokerAccountRepository(self._session_factory),
        )

    async def _start_providers(self) -> None:
        self._provider_manager = ProviderManager()
        factory = ProviderFactory(self._session_factory)
        providers = factory.create_all_providers(self._settings.providers, environment=self._active_environment)
        for provider in providers:
            self._provider_manager.register(provider)
        await self._provider_manager.connect_all()
        self._logger.info("Provider Manager initialized with %d connected providers", len(providers))

    async def _start_ingestion(self) -> None:
        """Initialize the Ingestion Service with adapters and repositories (Phase 8)."""
        from aios.providers import (
            MarketDataProvider,
            ShariahDataProvider,
            FundamentalDataProvider,
            NewsDataProvider,
        )
        from aios.providers.provider_adapters import (
            MarketDataProviderAdapter,
            ShariahDataProviderAdapter,
            FundamentalDataProviderAdapter,
            NewsDataProviderAdapter,
        )

        settings = self._settings
        if settings is None:
            return

        # Create adapters from connected providers
        market_adapter = None
        shariah_adapter = None
        fundamental_adapter = None
        news_adapter = None

        if self._provider_manager:
            for provider in self._provider_manager.list_providers():
                if isinstance(provider, MarketDataProvider):
                    market_adapter = MarketDataProviderAdapter(provider)
                elif isinstance(provider, ShariahDataProvider):
                    shariah_adapter = ShariahDataProviderAdapter(provider)
                elif isinstance(provider, FundamentalDataProvider):
                    fundamental_adapter = FundamentalDataProviderAdapter(provider)
                elif isinstance(provider, NewsDataProvider):
                    news_adapter = NewsDataProviderAdapter(provider)

        # Build ingestion config from settings
        ingestion_config = IngestionConfig(
            batch_size=settings.ingestion.batch_size,
            rate_limit_ms=settings.ingestion.rate_limit_ms,
            max_concurrent=settings.ingestion.max_concurrent,
            quarantine_on_warning=settings.ingestion.quarantine_on_warning,
            freshness_max_age_days=settings.ingestion.freshness_max_age_days,
            default_exchange=settings.ingestion.default_exchange,
        )

        # Create IngestionService with adapters and repositories
        self._ingestion_service = IngestionService(
            pipeline=DataPipeline(DataValidator()),
            validator=DataValidator(),
            market_adapter=market_adapter,
            shariah_adapter=shariah_adapter,
            fundamental_adapter=fundamental_adapter,
            news_adapter=news_adapter,
            market_repository=MarketRepository(self._session_factory) if market_adapter else None,
            shariah_repository=ShariahRepository(self._session_factory) if shariah_adapter else None,
            fundamental_repository=CompanyRepository(self._session_factory) if fundamental_adapter else None,
            news_repository=NewsRepository(self._session_factory) if news_adapter else None,
            config=ingestion_config,
        )
        self._wire_signal_news_engine(news_adapter)
        self._logger.info(
            "Ingestion Service initialized (adapters: market=%s, shariah=%s, fundamental=%s, news=%s)",
            market_adapter is not None,
            shariah_adapter is not None,
            fundamental_adapter is not None,
            news_adapter is not None,
        )

    def _wire_signal_news_engine(self, news_adapter: "NewsDataProviderAdapter | None") -> None:
        """Build and attach the News Intelligence Engine to the Signal Engine.

        The Signal Engine is registered before providers connect (AIOS-104
        section 4), so its News Engine is built here, once the connected News
        provider adapter is available, and attached to the registered Signal
        Engine (AIOS-605 section 10, AIOS-405 section 11).
        """
        if news_adapter is None or self._engine_manager is None:
            return
        signal_engines = self._engine_manager.get_by_type(EngineType.SIGNAL)
        if not signal_engines:
            return
        news_engine = NewsEngine(news_adapter)
        signal_engines[0].attach_news_engine(news_engine)
        self._logger.info("News Engine attached to Signal Engine")

    def _validate_ready(self) -> None:
        missing: list[str] = []
        if self._settings is None:
            missing.append("configuration")
        if self._root_logger is None:
            missing.append("logging")
        if self._db_engine is None:
            missing.append("database")
        if self._bus is None:
            missing.append("event_bus")
        if self._agent_manager is None or len(self._agent_manager.list_agents()) != len(AgentType):
            missing.append("agents")
        if self._engine_manager is None or len(self._engine_manager.list_engines()) != len(
            EngineType
        ):
            missing.append("engines")
        if self._provider_manager is None:
            missing.append("providers")
        if missing:
            raise CoreBootstrapError(
                f"Core Engine readiness validation failed: {', '.join(missing)}"
            )

    async def _publish_system_event(self, event_type: str) -> None:
        if self._bus is None:
            return
        event = Event(
            event_type=event_type,
            source="core.engine",
            priority=EventPriority.MEDIUM,
        )
        await self._bus.publish(event)

    async def _rollback(self) -> None:
        self._logger.warning("Rolling back partially initialized Core Engine")
        await self._teardown_components()

    async def _teardown_components(self) -> None:
        errors: list[Exception] = []
        if self._metrics_server is not None:
            try:
                await self._stop_metrics()
            except Exception as exc:  # noqa: BLE001 - teardown must not mask errors
                errors.append(exc)
        if self._order_timeout_task is not None:
            self._order_timeout_task.cancel()
            try:
                await self._order_timeout_task
            except asyncio.CancelledError:
                pass
            self._order_timeout_task = None
        if self._alert_manager is not None:
            try:
                await self._alert_manager.stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        if self._broker_service is not None and self._event_log is not None:
            self._event_log.record(
                EVENT_BROKER_DISCONNECTED,
                "core.engine",
                payload={"source": "core.engine", "reason": "system shutdown"},
            )
        if self._ingestion_service is not None:
            try:
                # IngestionService doesn't have explicit cleanup, but we clear the reference
                self._ingestion_service = None
            except Exception as exc:  # noqa: BLE001 - teardown must not mask errors
                errors.append(exc)
        if self._provider_manager is not None:
            try:
                await self._provider_manager.disconnect_all()
            except Exception as exc:  # noqa: BLE001 - teardown must not mask errors
                errors.append(exc)
        if self._engine_manager is not None:
            for engine in self._engine_manager.list_engines():
                try:
                    self._engine_manager.unregister(engine.engine_id)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        if self._agent_manager is not None:
            for agent in self._agent_manager.list_agents():
                try:
                    self._agent_manager.unregister(agent.agent_id)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        if self._db_engine is not None:
            try:
                self._db_engine.dispose()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        if errors:
            self._logger.warning("Core Engine teardown reported %d error(s)", len(errors))
