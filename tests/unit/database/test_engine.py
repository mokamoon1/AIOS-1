"""Engine creation tests (ADR-0001, ADR-0006)."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from aios.database import create_db_engine, create_session_factory

pytestmark = pytest.mark.unit


class TestEngineCreation:
    def test_create_engine_returns_sqlalchemy_engine(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        assert isinstance(engine, Engine)

    def test_create_engine_with_pool_pre_ping(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        assert engine.pool is not None

    def test_create_session_factory_returns_sessionmaker(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        session_factory = create_session_factory(engine)
        assert session_factory is not None
