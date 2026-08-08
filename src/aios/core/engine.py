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

import logging
from enum import Enum
from pathlib import Path
from typing import Any

from aios.agents import AgentManager
from aios.agents.roster import AgentType, PortfolioAgent, create_agent
from aios.agents.types import AgentState
from aios.brokers import BrokerService, PaperBroker, PaperOrderCoordinator
from aios.config import AppSettings, Environment, get_environment, load_settings
from aios.core.exceptions import CoreBootstrapError, CoreStateError
from aios.data.pipeline import DataPipeline
from aios.data.services import DataService
from aios.data.validation import DataValidator
from aios.database import create_db_engine, create_session_factory
from aios.database.repositories import (
    BrokerAccountRepository,
    CompanyRepository,
    DecisionRepository,
    MarketRepository,
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
from aios.portfolio import PortfolioService
from aios.providers import ProviderManager


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
    ) -> None:
        self._environment = environment
        self._config_dir = config_dir
        self._logger = logger or logging.getLogger("aios.core.engine")
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
        self._data_access: DataService | None = None
        self._broker_service: BrokerService | None = None
        self._paper_coordinator: PaperOrderCoordinator | None = None
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
            await self._start_broker()
            await self._start_providers()
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
            },
        }

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
        for engine_type in EngineType:
            manager.register(create_engine(engine_type, bus=self._bus, data_access=data_access))
        self._engine_manager = manager
        self._wire_portfolio_agent(data_access)
        self._logger.info("Engine Manager loaded %d engines", len(manager.list_engines()))

    async def _start_broker(self) -> None:
        """Wire the authorized Paper Broker (PAPER environment only, AIOS-603 section 11).

        The Paper Broker is constructed only in the Paper environment: its
        order book, fills, positions, and account are persisted through the
        Data Layer facade (AIOS-606 section 1), and approved decisions are
        routed through the coordinator under ``SUBMIT_PAPER_ORDERS``
        authorization (AIOS-408 section 8, AIOS-406 section 13). No live
        broker and no production execution are ever wired (AIOS-208 section 8).
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
        self._broker_service = BrokerService(paper_broker, store=data_access)
        self._paper_coordinator = PaperOrderCoordinator(self._broker_service, data_access)
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
        self._logger.info("Provider Manager initialized (no providers connected)")

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
