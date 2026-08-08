"""Portfolio repository behavior tests (AIOS-606, AIOS-402)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.data.models import PortfolioPosition, PositionStatus
from aios.database.exceptions import RecordNotFoundError
from aios.database.repositories import PortfolioRepository

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_BASE = datetime(2026, 8, 1, 12, 0, tzinfo=_UTC)


def _position(
    symbol: str = "AAPL",
    exchange: str = "NASDAQ",
    sector: str = "Technology",
    status: PositionStatus = PositionStatus.OPEN,
    updated_at: datetime | None = None,
    allocation: float = 0.4,
    quantity: float = 100.0,
    current_price: float = 100.0,
) -> PortfolioPosition:
    return PortfolioPosition(
        symbol=symbol,
        exchange=exchange,
        quantity=quantity,
        entry_price=90.0,
        current_price=current_price,
        allocation=allocation,
        sector=sector,
        status=status,
        updated_at=updated_at or _BASE,
    )


class TestPortfolioRepository:
    def test_upsert_and_get(self, session_factory) -> None:
        repo = PortfolioRepository(session_factory)
        repo.upsert_position(_position())
        got = repo.get_position("AAPL", "NASDAQ")
        assert got.symbol == "AAPL"
        assert got.exchange == "NASDAQ"
        assert got.quantity == 100.0
        assert got.entry_price == 90.0
        assert got.current_price == 100.0
        assert got.allocation == 0.4
        assert got.sector == "Technology"
        assert got.status is PositionStatus.OPEN
        assert got.updated_at == _BASE

    def test_upsert_updates_existing_position(self, session_factory) -> None:
        repo = PortfolioRepository(session_factory)
        repo.upsert_position(_position())
        later = _BASE + timedelta(days=1)
        repo.upsert_position(
            _position(
                quantity=150.0,
                current_price=110.0,
                allocation=0.5,
                updated_at=later,
            )
        )
        positions = repo.list_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 150.0
        assert positions[0].current_price == 110.0
        assert positions[0].allocation == 0.5
        assert positions[0].updated_at == later

    def test_get_unknown_symbol_raises(self, session_factory) -> None:
        repo = PortfolioRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.get_position("NOPE", "NASDAQ")

    def test_list_positions_filters_by_status(self, session_factory) -> None:
        repo = PortfolioRepository(session_factory)
        repo.upsert_position(_position(symbol="AAPL"))
        repo.upsert_position(_position(symbol="MSFT", status=PositionStatus.CLOSED, allocation=0.0))
        open_positions = repo.list_positions(status=PositionStatus.OPEN)
        closed_positions = repo.list_positions(status=PositionStatus.CLOSED)
        assert [p.symbol for p in open_positions] == ["AAPL"]
        assert [p.symbol for p in closed_positions] == ["MSFT"]
        assert len(repo.list_positions()) == 2

    def test_get_positions_by_sector_returns_only_open(self, session_factory) -> None:
        repo = PortfolioRepository(session_factory)
        repo.upsert_position(_position(symbol="AAPL", sector="Technology"))
        repo.upsert_position(
            _position(
                symbol="MSFT", sector="Technology", status=PositionStatus.CLOSED, allocation=0.0
            )
        )
        repo.upsert_position(_position(symbol="JNJ", sector="Healthcare"))
        tech = repo.get_positions_by_sector("Technology")
        assert [p.symbol for p in tech] == ["AAPL"]

    def test_same_symbol_different_exchange_are_distinct(self, session_factory) -> None:
        repo = PortfolioRepository(session_factory)
        repo.upsert_position(_position(exchange="NASDAQ"))
        repo.upsert_position(_position(exchange="NYSE"))
        assert len(repo.list_positions()) == 2
