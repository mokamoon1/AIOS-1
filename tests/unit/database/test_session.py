"""Session lifecycle tests (ADR-0001, AIOS-606)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from aios.database import create_db_engine, create_session_factory, session_scope

pytestmark = pytest.mark.unit


class TestSessionLifecycle:
    def test_session_opens_and_closes(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        session_factory = create_session_factory(engine)
        with session_scope(session_factory) as session:
            assert isinstance(session, Session)

    def test_session_rolls_back_on_error(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        session_factory = create_session_factory(engine)
        with (
            pytest.raises(RuntimeError),
            patch.object(Session, "rollback") as mock_rollback,
            session_scope(session_factory),
        ):
            raise RuntimeError("boom")
        mock_rollback.assert_called_once()

    def test_session_closes_after_scope(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        session_factory = create_session_factory(engine)
        with patch.object(Session, "close") as mock_close, session_scope(session_factory):
            pass
        mock_close.assert_called_once()

    def test_session_commits_on_success(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        session_factory = create_session_factory(engine)
        with patch.object(Session, "commit") as mock_commit, session_scope(session_factory):
            pass
        mock_commit.assert_called_once()
