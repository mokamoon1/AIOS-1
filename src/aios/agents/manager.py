"""Agent Manager: loading, registration, permissions, and status (AIOS-104
section 5.3).

The Core Engine defines an Agent Manager responsible for:

* Loading agents.
* Registering agents.
* Managing permissions.
* Monitoring agent status.

This manager keeps a registry of agents, initializes them on registration,
routes execution requests to the correct agent, and reports a status map
for monitoring.
"""

from __future__ import annotations

import logging

from aios.agents.base import Agent
from aios.agents.exceptions import AgentNotFoundError, AgentRegistrationError
from aios.agents.messages import AgentContext, AgentResult
from aios.agents.types import AgentState, AgentType


class AgentManager:
    """Registry and execution coordinator for AIOS agents (AIOS-104
    section 5.3).

    Each agent is registered once under its ``agent_id``; registration
    initializes the agent (lifecycle stage 1). Execution is routed by
    ``agent_id`` or by the first matching ``AgentType``.
    """

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._agents: dict[str, Agent] = {}
        self._logger = logger or logging.getLogger("aios.agents.manager")

    def register(self, agent: Agent) -> None:
        """Register and initialize ``agent`` (AIOS-104 section 5.3)."""
        if agent.agent_id in self._agents:
            raise AgentRegistrationError(f"Agent {agent.agent_id!r} is already registered")
        if agent.state is not AgentState.UNINITIALIZED:
            raise AgentRegistrationError(
                f"Agent {agent.agent_id!r} must be uninitialized before registration"
            )
        agent.initialize()
        self._agents[agent.agent_id] = agent
        self._logger.info("Registered agent %s (%s)", agent.agent_id, agent.agent_type.value)

    def unregister(self, agent_id: str) -> None:
        """Shut down and remove ``agent_id`` from the registry."""
        agent = self.get(agent_id)
        agent.shutdown()
        del self._agents[agent_id]
        self._logger.info("Unregistered agent %s", agent_id)

    def get(self, agent_id: str) -> Agent:
        """Return the registered agent with ``agent_id``."""
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"No registered agent with id {agent_id!r}")
        return self._agents[agent_id]

    def get_by_type(self, agent_type: AgentType) -> list[Agent]:
        """Return all registered agents of ``agent_type``."""
        return [a for a in self._agents.values() if a.agent_type is agent_type]

    def list_agents(self) -> list[Agent]:
        """Return all registered agents in registration order."""
        return list(self._agents.values())

    def status(self) -> dict[str, AgentState]:
        """Return a map of agent_id -> current lifecycle state."""
        return {agent_id: agent.state for agent_id, agent in self._agents.items()}

    async def execute(self, agent_id: str, context: AgentContext) -> AgentResult:
        """Execute ``context`` against the agent identified by ``agent_id``."""
        return await self.get(agent_id).execute(context)

    async def execute_by_type(self, agent_type: AgentType, context: AgentContext) -> AgentResult:
        """Execute ``context`` against the first agent of ``agent_type``."""
        agents = self.get_by_type(agent_type)
        if not agents:
            raise AgentNotFoundError(f"No registered agent of type {agent_type.value!r}")
        return await agents[0].execute(context)
