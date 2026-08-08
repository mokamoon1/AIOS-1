"""Engine base class and lifecycle orchestration (AIOS-605).

Every AIOS engine follows the documented lifecycle (AIOS-605 section 4):
Initialize -> Load Data -> Validate Input -> Execute Analysis -> Generate
Results -> Validate Results -> Publish Output. Each engine exposes the
standard interface (AIOS-605 section 5): initialize, execute,
validate_input, validate_output, explain, shutdown.

Engines remain stateless during execution, consume standardized data only,
avoid provider-specific logic, and never manipulate the database directly
(AIOS-605 section 13). Failures detect invalid input, preserve execution
logs, report to the Event Bus, and never propagate corrupted results
(AIOS-605 section 15). Monitoring records execution count, duration,
failure rate, and confidence distribution (AIOS-605 section 16).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date
from typing import Any, ClassVar, Protocol
from uuid import uuid4

from aios.data.models import (
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    InvestmentDecision,
    PortfolioPosition,
    PositionStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.engines.exceptions import EngineStateError, EngineValidationError
from aios.engines.messages import EngineInput, EngineOutput
from aios.engines.types import EngineState, EngineType
from aios.errors import DataError, EngineError, ErrorEventPublisher
from aios.events import Event, EventBus, EventPriority


class DataAccess(Protocol):
    """Read facade consumed by engines (AIOS-501 section 2, AIOS-605 section 13).

    The concrete :class:`aios.data.services.DataService` satisfies this
    protocol. Engines consume standardized data only through this facade and
    never touch providers or the database directly.
    """

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: Any | None = None,
        end: Any | None = None,
        limit: int = 1000,
    ) -> Sequence[Candle]: ...

    def get_fundamentals(
        self, symbol: str, *, report_date: date | None = None
    ) -> CompanyFundamentals: ...

    def get_compliance_status(
        self, symbol: str, *, as_of: date | None = None
    ) -> ShariahCompliance: ...

    def list_positions(
        self, *, status: PositionStatus | None = None
    ) -> Sequence[PortfolioPosition]: ...

    def store_decisions(self, decisions: list[InvestmentDecision]) -> int: ...


class Engine(ABC):
    """Base class for all AIOS engines (AIOS-605).

    Subclasses declare their ``engine_type``, ``name``, ``version``, and
    ``description`` and implement ``_load_data`` and ``_analyze``. The
    lifecycle is managed by the base class; engines never modify another
    engine's internal state and communicate only through standardized data
    models and the Event Bus (AIOS-605 sections 12 and 13).
    """

    engine_type: ClassVar[EngineType]
    name: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = ""
    dependencies: ClassVar[frozenset[EngineType]] = frozenset()
    can_issue_recommendation: ClassVar[bool] = False

    def __init__(
        self,
        *,
        engine_id: str | None = None,
        bus: EventBus | None = None,
        logger: logging.Logger | None = None,
        data_access: DataAccess | None = None,
    ) -> None:
        if not self.engine_type:
            raise TypeError("Engine subclasses must declare engine_type")
        self._engine_id = engine_id or f"{self.engine_type.value}-{uuid4().hex[:8]}"
        self._bus = bus
        self._logger = logger or logging.getLogger(f"aios.engines.{self.engine_type.value}")
        self._data_access = data_access
        self._state = EngineState.UNINITIALIZED
        self._execution_count = 0
        self._failure_count = 0
        self._total_duration = 0.0
        self._confidence_history: list[float] = []

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def state(self) -> EngineState:
        return self._state

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def data_access(self) -> DataAccess | None:
        return self._data_access

    def initialize(self) -> None:
        """Initialize the engine (lifecycle stage 1)."""
        self._transition(EngineState.INITIALIZED, allowed={EngineState.UNINITIALIZED})
        self._on_initialize()
        self.logger.info("Engine %s (%s) initialized", self.engine_id, self.engine_type.value)

    def reset(self) -> None:
        """Return the engine to the initialized state (AIOS-605 section 4)."""
        self._transition(
            EngineState.INITIALIZED,
            allowed={EngineState.INITIALIZED, EngineState.IDLE, EngineState.FAILED},
        )
        self._on_reset()

    def shutdown(self) -> None:
        """Shut the engine down (AIOS-605 section 5)."""
        self._transition(EngineState.SHUTDOWN, allowed=set(EngineState) - {EngineState.SHUTDOWN})
        self._on_shutdown()
        self.logger.info("Engine %s (%s) shut down", self.engine_id, self.engine_type.value)

    async def execute(self, engine_input: EngineInput) -> EngineOutput:
        """Run the full engine lifecycle (AIOS-605 section 4).

        The pipeline is: Load Data, Validate Input, Execute Analysis and
        Generate Results (``_analyze``), Validate Results, Publish Output.
        A failed execution quarantines the engine in the ``failed`` state
        and notifies the Event Bus so corrupted results are never propagated
        (AIOS-605 section 15).
        """
        self._transition(
            EngineState.PROCESSING,
            allowed={EngineState.INITIALIZED, EngineState.IDLE},
        )
        started = time.perf_counter()
        try:
            data = await self._load_data(engine_input)
            if not self.validate_input(engine_input):
                raise EngineValidationError(
                    f"Engine {self.engine_id} rejected input for request {engine_input.request_id}"
                )
            result = await self._analyze(engine_input, data)
            result.engine_id = self._engine_id
            result.processing_duration = time.perf_counter() - started
            if not self.validate_output(result):
                raise EngineValidationError(
                    f"Engine {self.engine_id} produced invalid output for request "
                    f"{engine_input.request_id}"
                )
            await self._publish_result(result)
            self._record_success(result)
            self._state = EngineState.IDLE
            self.logger.info(
                "Engine %s (%s) completed request %s",
                self.engine_id,
                self.engine_type.value,
                engine_input.request_id,
            )
            return result
        except Exception as exc:  # noqa: BLE001 - fail-safe boundary
            self._record_failure()
            self._state = EngineState.FAILED
            self.logger.exception(
                "Engine %s (%s) failed request %s",
                self.engine_id,
                self.engine_type.value,
                engine_input.request_id,
            )
            if self._bus is not None:
                await ErrorEventPublisher(self._bus).publish(
                    source=self.engine_type.value,
                    component=self.name,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    details={
                        "engine_id": self.engine_id,
                        "request_id": engine_input.request_id,
                    },
                )
            if isinstance(exc, EngineError):
                raise
            raise EngineError(f"Engine {self.engine_id} failed: {exc}") from exc

    def validate_input(self, engine_input: EngineInput) -> bool:
        """Validate engine input (Validate Input stage, AIOS-605 section 4).

        Subclasses may override to add domain-specific checks. The base
        implementation accepts any well-formed :class:`EngineInput`.
        """
        return True

    def validate_output(self, result: EngineOutput) -> bool:
        """Validate engine output (Validate Results stage, AIOS-605 section 4).

        Subclasses may override to add domain-specific checks. The base
        implementation rejects results whose output is missing.
        """
        return bool(result.output)

    def require_compliant(self, symbol: str) -> None:
        """Block analysis of a security that is not Shariah-approved (FR-002).

        Implements the documented gate that only approved securities may enter
        analysis (AIOS-301 FR-002, AIOS-205 section 3, AIOS-305 section 3):
        non-compliant, under-review, and unknown securities are rejected and
        unknown compliance cannot be resolved from the data facade.
        """
        if self._data_access is None:
            raise EngineValidationError(
                "Cannot verify Shariah compliance without a data access facade"
            )
        try:
            record = self._data_access.get_compliance_status(symbol)
        except DataError as exc:
            raise EngineValidationError(
                f"Cannot verify Shariah compliance for {symbol}: {exc}"
            ) from exc
        if record.compliance_status is not ComplianceStatus.COMPLIANT:
            raise EngineValidationError(
                f"Security {symbol} is not Shariah-approved "
                f"(status: {record.compliance_status.value}); analysis blocked"
            )

    def explain(self, result: EngineOutput) -> str:
        """Return the explanation for ``result`` (AIOS-605 section 5)."""
        return result.explanation

    def metrics(self) -> dict[str, Any]:
        """Return monitoring metrics (AIOS-605 section 16).

        The framework records execution count, total and average duration,
        failure rate, and confidence distribution. Resource utilization is
        measured by the runtime in a later step.
        """
        executions = self._execution_count
        return {
            "engine_id": self.engine_id,
            "engine_type": self.engine_type.value,
            "execution_count": executions,
            "failure_count": self._failure_count,
            "failure_rate": self._failure_count / executions if executions else 0.0,
            "total_duration_seconds": self._total_duration,
            "average_duration_seconds": self._total_duration / executions if executions else 0.0,
            "confidence_distribution": list(self._confidence_history),
        }

    @abstractmethod
    async def _load_data(self, engine_input: EngineInput) -> Any:
        """Load standardized data (Load Data stage, AIOS-605 section 4)."""

    @abstractmethod
    async def _analyze(self, engine_input: EngineInput, data: Any) -> EngineOutput:
        """Execute analysis and generate results (subclass hook)."""

    def _on_initialize(self) -> None:  # noqa: B027
        """Subclass hook invoked after initialization."""

    def _on_reset(self) -> None:  # noqa: B027
        """Subclass hook invoked after reset."""

    def _on_shutdown(self) -> None:  # noqa: B027
        """Subclass hook invoked after shutdown."""

    def _transition(self, target: EngineState, allowed: set[EngineState]) -> None:
        if self._state not in allowed:
            raise EngineStateError(
                f"Invalid engine {self.engine_id} transition "
                f"{self._state.value!r} -> {target.value!r}"
            )
        self._state = target

    def _record_success(self, result: EngineOutput) -> None:
        self._execution_count += 1
        self._total_duration += result.processing_duration
        self._confidence_history.append(result.confidence)

    def _record_failure(self) -> None:
        self._execution_count += 1
        self._failure_count += 1

    async def _publish_result(self, result: EngineOutput) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                source=self.engine_type.value,
                event_type="ENGINE_RESULT",
                priority=EventPriority.MEDIUM,
                payload={"result": result.model_dump(mode="json")},
            )
        )
