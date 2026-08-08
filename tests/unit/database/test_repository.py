"""Repository interface tests (ADR-0001, AIOS-606)."""

from __future__ import annotations

import pytest

from aios.database import Repository

pytestmark = pytest.mark.unit


class TestRepositoryInterface:
    def test_repository_protocol_members(self) -> None:
        for member in ("get", "list", "add", "update", "delete", "iterator"):
            assert hasattr(Repository, member), f"missing {member!r}"

    def test_repository_is_protocol(self) -> None:
        assert isinstance(Repository, type)
