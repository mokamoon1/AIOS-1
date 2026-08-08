"""Shared test fixtures (ADR-0001, ADR-0006).

SQLite is used for tests and local development only (ADR-0001, ADR-0006
section 5.2). An in-memory engine with a StaticPool shares one connection
across sessions so all tests see the same schema.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import aios.database.models  # noqa: F401  (register ORM models on Base.metadata)
from aios.database.base import Base
from aios.database.engine import create_session_factory


@pytest.fixture
def db_engine():
    """In-memory SQLite engine with all AIOS tables created."""
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    """Session factory bound to the shared in-memory engine."""
    return create_session_factory(db_engine)


def _candle(symbol: str = "AAPL", **overrides) -> dict:
    base = {
        "timestamp": "2026-08-01T13:30:00Z",
        "symbol": symbol,
        "timeframe": "1h",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 1000,
    }
    base.update(overrides)
    return base
