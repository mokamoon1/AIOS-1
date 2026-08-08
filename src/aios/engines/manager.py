"""Engine Manager: registration, lookup, status, and execution coordination
(AIOS-605 section 3).

The Engine Manager coordinates execution order and dependency resolution.
Each engine is registered once under its ``engine_id``; registration
initializes the engine (lifecycle stage 1). The manager also resolves a
valid execution order for a set of engine types based on the dependencies
each engine declares (AIOS-605 sections 10 and 11).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from aios.engines.base import Engine
from aios.engines.exceptions import (
    EngineDependencyError,
    EngineNotFoundError,
    EngineRegistrationError,
)
from aios.engines.messages import EngineInput, EngineOutput
from aios.engines.types import EngineState, EngineType


class EngineManager:
    """Registry and execution coordinator for AIOS engines (AIOS-605 section 3).

    Each engine is registered once under its ``engine_id``; registration
    initializes the engine (lifecycle stage 1). Execution is routed by
    ``engine_id`` or by the first matching ``EngineType``. The declared
    dependencies of registered engines drive execution-order resolution.
    """

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._engines: dict[str, Engine] = {}
        self._logger = logger or logging.getLogger("aios.engines.manager")

    def register(self, engine: Engine) -> None:
        """Register and initialize ``engine`` (AIOS-605 section 3)."""
        if engine.engine_id in self._engines:
            raise EngineRegistrationError(f"Engine {engine.engine_id!r} is already registered")
        if engine.state is not EngineState.UNINITIALIZED:
            raise EngineRegistrationError(
                f"Engine {engine.engine_id!r} must be uninitialized before registration"
            )
        engine.initialize()
        self._engines[engine.engine_id] = engine
        self._logger.info("Registered engine %s (%s)", engine.engine_id, engine.engine_type.value)

    def unregister(self, engine_id: str) -> None:
        """Shut down and remove ``engine_id`` from the registry."""
        engine = self.get(engine_id)
        engine.shutdown()
        del self._engines[engine_id]
        self._logger.info("Unregistered engine %s", engine_id)

    def get(self, engine_id: str) -> Engine:
        """Return the registered engine with ``engine_id``."""
        if engine_id not in self._engines:
            raise EngineNotFoundError(f"No registered engine with id {engine_id!r}")
        return self._engines[engine_id]

    def get_by_type(self, engine_type: EngineType) -> list[Engine]:
        """Return all registered engines of ``engine_type``."""
        return [e for e in self._engines.values() if e.engine_type is engine_type]

    def list_engines(self) -> list[Engine]:
        """Return all registered engines in registration order."""
        return list(self._engines.values())

    def status(self) -> dict[str, EngineState]:
        """Return a map of engine_id -> current lifecycle state."""
        return {engine_id: engine.state for engine_id, engine in self._engines.items()}

    def resolve_execution_order(self, engine_types: Iterable[EngineType]) -> list[EngineType]:
        """Resolve a valid execution order for ``engine_types``.

        The requested set is expanded with every registered dependency the
        engines declare, and the result is ordered so each engine executes
        only after every dependency it declares has executed. Cycles are
        rejected.

        Raises:
            EngineDependencyError: if the declared dependencies form a cycle.
            EngineNotFoundError: if a requested type has no registered engine.
        """
        by_type: dict[EngineType, Engine] = {}
        requested = list(engine_types)
        for engine_type in requested:
            engines = self.get_by_type(engine_type)
            if not engines:
                raise EngineNotFoundError(f"No registered engine of type {engine_type.value!r}")
            by_type[engine_type] = engines[0]
        # Expand the requested set with registered dependencies.
        to_visit = list(requested)
        included = set(requested)
        while to_visit:
            engine_type = to_visit.pop()
            for dependency in by_type[engine_type].dependencies:
                if dependency in included:
                    continue
                engines = self.get_by_type(dependency)
                if engines:
                    by_type[dependency] = engines[0]
                    included.add(dependency)
                    to_visit.append(dependency)
        deps: dict[EngineType, set[EngineType]] = {
            t: {d for d in by_type[t].dependencies if d in included} for t in included
        }
        resolved: list[EngineType] = []
        remaining = set(included)
        while remaining:
            ready = [t for t in remaining if not (deps[t] & remaining)]
            if not ready:
                cycle = ", ".join(sorted(t.value for t in remaining))
                raise EngineDependencyError(f"Circular engine dependencies among: {cycle}")
            for engine_type in sorted(ready, key=lambda t: t.value):
                resolved.append(engine_type)
                remaining.discard(engine_type)
        return resolved

    async def execute(self, engine_id: str, engine_input: EngineInput) -> EngineOutput:
        """Execute ``engine_input`` against the engine identified by ``engine_id``."""
        return await self.get(engine_id).execute(engine_input)

    async def execute_by_type(
        self, engine_type: EngineType, engine_input: EngineInput
    ) -> EngineOutput:
        """Execute ``engine_input`` against the first engine of ``engine_type``."""
        engines = self.get_by_type(engine_type)
        if not engines:
            raise EngineNotFoundError(f"No registered engine of type {engine_type.value!r}")
        return await engines[0].execute(engine_input)

    async def run_pipeline(
        self, engine_types: Iterable[EngineType], engine_input: EngineInput
    ) -> dict[EngineType, EngineOutput]:
        """Execute ``engine_input`` through ``engine_types`` in dependency order.

        Each engine is executed in the resolved dependency order (AIOS-605
        section 3) and the outputs of every earlier engine are supplied to
        the next engine through the standardized ``engine_outputs`` payload
        key, so the Decision Engine can aggregate prior analysis and risk
        outputs (AIOS-605 section 11). Returns the results keyed by engine
        type.
        """
        order = self.resolve_execution_order(engine_types)
        results: dict[EngineType, EngineOutput] = {}
        for engine_type in order:
            engines = self.get_by_type(engine_type)
            if not engines:
                raise EngineNotFoundError(f"No registered engine of type {engine_type.value!r}")
            payload = dict(engine_input.payload)
            if results:
                payload["engine_outputs"] = {
                    engine.value: result.model_dump(mode="json")
                    for engine, result in results.items()
                }
            input_for_engine = EngineInput(
                request_id=engine_input.request_id,
                payload=payload,
                input_version=engine_input.input_version,
            )
            results[engine_type] = await engines[0].execute(input_for_engine)
        return results
