"""Backtest Repository - Persistence for backtest runs and results (Phase 9.5).

Follows the existing Repository Pattern (ADR-0006) using SQLAlchemy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from aios.backtest.models import BacktestRun, BacktestResult, BacktestStatus, EquityPoint, BacktestConfig
from aios.database.base import Base
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import BacktestRunModel, BacktestEquityPointModel
from aios.database.repositories.base import BaseRepository


class BacktestRepository(BaseRepository[BacktestRunModel]):
    """Repository for backtest runs and results."""

    entity_type = BacktestRunModel

    def add_run(self, run: BacktestRun) -> None:
        """Insert a new backtest run."""
        with session_scope(self._session_factory) as session:
            row = BacktestRunModel(
                id=run.id,
                config=run.config.model_dump(mode="json"),
                status=run.status.value,
                started_at=run.started_at,
                completed_at=run.completed_at,
                error=run.error,
                result=run.result.model_dump(mode="json") if run.result else None,
            )
            session.add(row)

    def update_run_status(
        self,
        run_id: UUID,
        status: BacktestStatus,
        *,
        completed_at: datetime | None = None,
        error: str | None = None,
        result: BacktestResult | None = None,
    ) -> None:
        """Update backtest run status and results."""
        with session_scope(self._session_factory) as session:
            row = session.get(BacktestRunModel, run_id)
            if row is None:
                raise RecordNotFoundError(f"Backtest run {run_id!r} not found")
            row.status = status.value
            if completed_at is not None:
                row.completed_at = completed_at
            if error is not None:
                row.error = error
            if result is not None:
                row.result = result.model_dump(mode="json")

    def get_run(self, run_id: UUID) -> BacktestRun:
        """Retrieve a backtest run by ID."""
        with session_scope(self._session_factory) as session:
            row = session.get(BacktestRunModel, run_id)
            if row is None:
                raise RecordNotFoundError(f"Backtest run {run_id!r} not found")
            session.expunge(row)
            return self._row_to_run(row)

    def list_runs(
        self,
        *,
        status: BacktestStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BacktestRun]:
        """List backtest runs with optional filtering."""
        with session_scope(self._session_factory) as session:
            stmt = select(BacktestRunModel).order_by(BacktestRunModel.started_at.desc()).limit(limit).offset(offset)
            if status is not None:
                stmt = stmt.where(BacktestRunModel.status == status.value)
            rows = session.scalars(stmt).all()
            for row in rows:
                session.expunge(row)
            return [self._row_to_run(row) for row in rows]

    def add_equity_points(self, run_id: UUID, points: list[EquityPoint]) -> int:
        """Bulk insert equity curve points for a backtest run."""
        if not points:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            for point in points:
                session.add(BacktestEquityPointModel(
                    run_id=run_id,
                    timestamp=point.timestamp,
                    equity=point.equity,
                    cash=point.cash,
                    market_value=point.market_value,
                    daily_return=point.daily_return,
                    cumulative_return=point.cumulative_return,
                ))
                stored += 1
        return stored

    def get_equity_curve(self, run_id: UUID) -> list[EquityPoint]:
        """Retrieve equity curve for a backtest run."""
        with session_scope(self._session_factory) as session:
            stmt = (
                select(BacktestEquityPointModel)
                .where(BacktestEquityPointModel.run_id == run_id)
                .order_by(BacktestEquityPointModel.timestamp)
            )
            rows = session.scalars(stmt).all()
            # Expunge all objects to avoid DetachedInstanceError
            for row in rows:
                session.expunge(row)
            return [
                EquityPoint(
                    timestamp=row.timestamp,
                    equity=row.equity,
                    cash=row.cash,
                    market_value=row.market_value,
                    daily_return=row.daily_return,
                    cumulative_return=row.cumulative_return,
                )
                for row in rows
            ]

    def _row_to_run(self, row: BacktestRunModel) -> BacktestRun:
        """Convert database row to BacktestRun domain model."""
        config = BacktestConfig.model_validate(row.config)
        result = BacktestResult.model_validate(row.result) if row.result else None
        return BacktestRun(
            id=row.id,
            config=config,
            status=BacktestStatus(row.status),
            started_at=row.started_at,
            completed_at=row.completed_at,
            error=row.error,
            result=result,
        )