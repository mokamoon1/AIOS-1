"""Tests for the Portfolio module (AIOS-206, AIOS-306, AIOS-603 section 10)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from aios.data.models import PortfolioPosition, PositionStatus
from aios.errors import DataError
from aios.portfolio import PortfolioError, PortfolioService
from aios.portfolio.models import PortfolioSnapshot


def _position(
    symbol: str,
    *,
    quantity: float,
    entry_price: float,
    current_price: float,
    allocation: float,
    sector: str = "Technology",
    status: PositionStatus = PositionStatus.OPEN,
) -> PortfolioPosition:
    return PortfolioPosition(
        symbol=symbol,
        exchange="NASDAQ",
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price,
        allocation=allocation,
        sector=sector,
        status=status,
    )


class _FakeReader:
    def __init__(self, positions: list[PortfolioPosition]) -> None:
        self._positions = positions

    def list_positions(
        self, *, status: PositionStatus | None = None
    ) -> Sequence[PortfolioPosition]:
        if status is None:
            return self._positions
        return [p for p in self._positions if p.status is status]


class _FailingReader:
    def list_positions(
        self, *, status: PositionStatus | None = None
    ) -> Sequence[PortfolioPosition]:
        raise DataError("storage unavailable")


def _sample_positions() -> list[PortfolioPosition]:
    return [
        _position(
            "AAPL",
            quantity=10.0,
            entry_price=100.0,
            current_price=110.0,
            allocation=0.5,
            sector="Technology",
        ),
        _position(
            "MSFT",
            quantity=5.0,
            entry_price=200.0,
            current_price=180.0,
            allocation=0.3,
            sector="Technology",
        ),
        _position(
            "JNJ",
            quantity=10.0,
            entry_price=50.0,
            current_price=60.0,
            allocation=0.2,
            sector="Healthcare",
        ),
    ]


def test_build_snapshot_computes_objective_metrics() -> None:
    service = PortfolioService()
    snapshot = service.build_snapshot(_sample_positions())
    assert isinstance(snapshot, PortfolioSnapshot)
    assert snapshot.position_count == 3
    assert snapshot.sector_count == 2
    assert snapshot.total_value == pytest.approx(110 * 10 + 180 * 5 + 60 * 10)
    assert snapshot.max_position_allocation == pytest.approx(0.5)
    assert snapshot.max_sector_allocation == pytest.approx(2000 / 2600)
    assert snapshot.weighted_return_pct == pytest.approx(0.5 * 10.0 + 0.3 * (-10.0) + 0.2 * 20.0)


def test_build_snapshot_holding_metrics() -> None:
    service = PortfolioService()
    snapshot = service.build_snapshot(_sample_positions())
    aapl = next(p for p in snapshot.positions if p.symbol == "AAPL")
    assert aapl.market_value == pytest.approx(1100.0)
    assert aapl.unrealized_pnl == pytest.approx(100.0)
    assert aapl.return_pct == pytest.approx(10.0)
    assert aapl.allocation == pytest.approx(0.5)


def test_build_snapshot_sector_distribution() -> None:
    service = PortfolioService()
    snapshot = service.build_snapshot(_sample_positions())
    technology = next(s for s in snapshot.sectors if s.sector == "Technology")
    assert technology.count == 2
    assert technology.market_value == pytest.approx(1100 + 900)
    assert technology.allocation == pytest.approx(2000 / 2600)
    healthcare = next(s for s in snapshot.sectors if s.sector == "Healthcare")
    assert healthcare.count == 1
    assert healthcare.allocation == pytest.approx(600 / 2600)
    assert snapshot.sectors[0].sector == "Technology"


def test_build_snapshot_ignores_closed_positions() -> None:
    positions = [
        _position(
            "AAPL",
            quantity=10.0,
            entry_price=100.0,
            current_price=110.0,
            allocation=0.5,
        ),
        _position(
            "MSFT",
            quantity=5.0,
            entry_price=200.0,
            current_price=180.0,
            allocation=0.3,
            status=PositionStatus.CLOSED,
        ),
    ]
    snapshot = PortfolioService().build_snapshot(positions)
    assert snapshot.position_count == 1
    assert [p.symbol for p in snapshot.positions] == ["AAPL"]


def test_build_snapshot_empty_portfolio() -> None:
    snapshot = PortfolioService().build_snapshot([])
    assert snapshot.total_value == 0.0
    assert snapshot.position_count == 0
    assert snapshot.sector_count == 0
    assert snapshot.max_position_allocation == 0.0
    assert snapshot.max_sector_allocation == 0.0
    assert snapshot.weighted_return_pct == 0.0


def test_current_snapshot_reads_open_positions() -> None:
    reader = _FakeReader(_sample_positions())
    service = PortfolioService(reader)
    snapshot = service.current_snapshot()
    assert snapshot.position_count == 3
    assert service.reader is reader


def test_current_snapshot_without_reader_raises() -> None:
    with pytest.raises(PortfolioError, match="positions reader"):
        PortfolioService().current_snapshot()


def test_current_snapshot_decorates_data_failures() -> None:
    service = PortfolioService(_FailingReader())
    with pytest.raises(PortfolioError, match="Could not read current positions"):
        service.current_snapshot()
