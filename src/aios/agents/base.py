"""Agent base class and lifecycle orchestration (AIOS-604).

Every AIOS agent follows the same lifecycle and exposes the standard
interface: initialize, execute, validate, explain, reset, shutdown
(AIOS-604 section 6). Execution drives the documented stages — receive
context, process information, generate result, validate output, publish
result, return to idle — and failures are logged, notified to the Event
Bus, and quarantined rather than producing invalid recommendations
(AIOS-604 section 15).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar
from uuid import uuid4

from aios.agents.exceptions import AgentStateError
from aios.agents.messages import AgentContext, AgentMessage, AgentResult, MessageStatus
from aios.agents.types import AgentState, AgentType
from aios.errors import AgentError, ErrorEventPublisher
from aios.events import Event, EventBus, EventPriority


class Agent(ABC):
    """Base class for all AIOS agents (AIOS-604).

    Subclasses declare their ``agent_type``, ``name``, ``version``, and
    ``description`` and implement ``_process``. The lifecycle is managed by
    the base class; agents never modify another agent's internal state
    (AIOS-604 section 5). Agents communicate only through the Event Bus
    (AIOS-604 section 14, ADR-0005 section 5.7).
    """

    agent_type: ClassVar[AgentType]
    name: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = ""
    can_issue_final_recommendation: ClassVar[bool] = False

    def __init__(
        self,
        *,
        agent_id: str | None = None,
        bus: EventBus | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if not self.agent_type:
            raise TypeError("Agent subclasses must declare agent_type")
        self._agent_id = agent_id or f"{self.agent_type.value}-{uuid4().hex[:8]}"
        self._bus = bus
        self._logger = logger or logging.getLogger(f"aios.agents.{self.agent_type.value}")
        self._state = AgentState.UNINITIALIZED

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def initialize(self) -> None:
        """Initialize the agent (lifecycle stage 1)."""
        self._transition(AgentState.INITIALIZED, allowed={AgentState.UNINITIALIZED})
        self._on_initialize()
        self.logger.info("Agent %s (%s) initialized", self.agent_id, self.agent_type.value)

    def reset(self) -> None:
        """Return the agent to the initialized state (AIOS-604 section 6)."""
        self._transition(
            AgentState.INITIALIZED,
            allowed={AgentState.INITIALIZED, AgentState.IDLE, AgentState.FAILED},
        )
        self._on_reset()

    def shutdown(self) -> None:
        """Shut the agent down (AIOS-604 section 6)."""
        self._transition(AgentState.SHUTDOWN, allowed=set(AgentState) - {AgentState.SHUTDOWN})
        self._on_shutdown()
        self.logger.info("Agent %s (%s) shut down", self.agent_id, self.agent_type.value)

    async def execute(self, context: AgentContext) -> AgentResult:
        """Run the full agent lifecycle for ``context`` (AIOS-604 section 4).

        The result is validated before publication; a failed execution
        quarantines the agent in the ``failed`` state and notifies the Event
        Bus so invalid recommendations are never produced (AIOS-604
        section 15).
        """
        self._transition(
            AgentState.PROCESSING,
            allowed={AgentState.INITIALIZED, AgentState.IDLE},
        )
        try:
            result = await self._process(context)
            if not self.validate(result):
                raise AgentError(
                    f"Agent {self.agent_id} produced invalid output for request "
                    f"{context.request_id}"
                )
            await self._publish_result(result)
            self._state = AgentState.IDLE
            self.logger.info(
                "Agent %s (%s) completed request %s",
                self.agent_id,
                self.agent_type.value,
                context.request_id,
            )
            return result
        except Exception as exc:  # noqa: BLE001 - fail-safe boundary
            self._state = AgentState.FAILED
            self.logger.exception(
                "Agent %s (%s) failed request %s",
                self.agent_id,
                self.agent_type.value,
                context.request_id,
            )
            if self._bus is not None:
                await ErrorEventPublisher(self._bus).publish(
                    source=self.agent_type.value,
                    component=self.name,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    details={
                        "agent_id": self.agent_id,
                        "request_id": context.request_id,
                    },
                )
            if isinstance(exc, AgentError):
                raise
            raise AgentError(f"Agent {self.agent_id} failed: {exc}") from exc

    def validate(self, result: AgentResult) -> bool:
        """Validate an agent result (Validate Output stage).

        Subclasses may override to add domain-specific checks. The base
        implementation rejects results whose output is missing.
        """
        return bool(result.output)

    def explain(self, result: AgentResult) -> str:
        """Return the explanation for ``result`` (AIOS-604 section 6)."""
        return result.explanation

    async def send_message(
        self,
        *,
        receiver: AgentType,
        request_id: str,
        payload: dict | None = None,
        confidence: float = 0.0,
        status: MessageStatus = MessageStatus.COMPLETED,
    ) -> AgentMessage:
        """Send a structured message to another agent (AIOS-604 section 14).

        Agents communicate exclusively through the Event Bus (ADR-0005
        section 5.7); direct access to another agent's internal memory is
        prohibited (AIOS-604 section 14).
        """
        if self._bus is None:
            raise AgentError(f"Agent {self.agent_id} has no Event Bus configured for messaging")
        message = AgentMessage(
            sender=self.agent_type,
            receiver=receiver,
            request_id=request_id,
            payload=payload or {},
            confidence=confidence,
            status=status,
        )
        await self._bus.publish(
            Event(
                source=self.agent_type.value,
                event_type="AGENT_MESSAGE",
                priority=EventPriority.MEDIUM,
                payload=message.model_dump(mode="json"),
            )
        )
        return message

    @abstractmethod
    async def _process(self, context: AgentContext) -> AgentResult:
        """Process information and generate a result (subclass hook)."""

    def _on_initialize(self) -> None:  # noqa: B027
        """Subclass hook invoked after initialization."""

    def _on_reset(self) -> None:  # noqa: B027
        """Subclass hook invoked after reset."""

    def _on_shutdown(self) -> None:  # noqa: B027
        """Subclass hook invoked after shutdown."""

    def _transition(self, target: AgentState, allowed: set[AgentState]) -> None:
        if self._state not in allowed:
            raise AgentStateError(
                f"Invalid agent {self.agent_id} transition "
                f"{self._state.value!r} -> {target.value!r}"
            )
        self._state = target

    async def _publish_result(self, result: AgentResult) -> None:
        if self._bus is None:
            return
        if self.can_issue_final_recommendation:
            event_type = "FINAL_RECOMMENDATION"
        else:
            event_type = "AGENT_RESULT"
        await self._bus.publish(
            Event(
                source=self.agent_type.value,
                event_type=event_type,
                priority=EventPriority.MEDIUM,
                payload={"result": result.model_dump(mode="json")},
            )
        )
