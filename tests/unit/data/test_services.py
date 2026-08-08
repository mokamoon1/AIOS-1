"""Internal Data Services facade tests (AIOS-501 section 2)."""

from __future__ import annotations

from datetime import date

import pytest

from aios.data.exceptions import DataNotFoundError
from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    DecisionAction,
    InvestmentDecision,
    MarketStatus,
    PortfolioPosition,
    PositionStatus,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.data.pipeline import DataPipeline
from aios.data.services import DataService
from aios.data.validation import DataValidator

pytestmark = pytest.mark.unit


class _FakeMarketRepository:
    def __init__(self, candles, security):
        self._candles = candles
        self._security = security

    def get_candles(self, *, symbol, timeframe, start=None, end=None, limit=1000):
        return self._candles

    def get_security(self, *, symbol, exchange):
        return self._security


class _FakeShariahRepository:
    def __init__(self, record):
        self._record = record

    def get_compliance_status(self, *, symbol, as_of=None):
        return self._record


class _FakeFundamentalRepository:
    def __init__(self, record):
        self._record = record

    def get_fundamentals(self, *, symbol, report_date=None):
        return self._record


class _FakePortfolioRepository:
    def __init__(self):
        self._positions: dict[tuple[str, str], PortfolioPosition] = {}

    def upsert_position(self, position):
        self._positions[(position.symbol, position.exchange)] = position
        return position

    def get_position(self, *, symbol, exchange):
        return self._positions[(symbol, exchange)]

    def list_positions(self, *, status=None):
        if status is None:
            return list(self._positions.values())
        return [p for p in self._positions.values() if p.status is status]

    def get_positions_by_sector(self, sector):
        return [
            p
            for p in self._positions.values()
            if p.status is PositionStatus.OPEN and p.sector == sector
        ]


class _FakeDecisionRepository:
    def __init__(self):
        self._decisions: list[InvestmentDecision] = []

    def add_decisions(self, decisions):
        self._decisions.extend(decisions)
        return len(decisions)

    def get_decisions(self, *, symbol, start=None, end=None, limit=1000):
        return [d for d in self._decisions if d.symbol == symbol][:limit]

    def get_latest_decision(self, symbol):
        matches = [d for d in self._decisions if d.symbol == symbol]
        return matches[-1]


def _service(repos=None) -> DataService:
    repos = repos or {}
    return DataService(
        DataPipeline(DataValidator()),
        market_repository=repos.get("market"),
        shariah_repository=repos.get("shariah"),
        fundamental_repository=repos.get("fundamental"),
        portfolio_repository=repos.get("portfolio"),
        decision_repository=repos.get("decision"),
    )


def _candle() -> Candle:
    return Candle(
        timestamp="2026-08-01T13:30:00Z",
        symbol="AAPL",
        timeframe=Timeframe.ONE_HOUR,
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000.0,
    )


def _security() -> Security:
    return Security(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_type=AssetType.EQUITY,
        currency="USD",
        trading_session="regular",
        timezone="America/New_York",
        market_status=MarketStatus.OPEN,
    )


class TestDataServiceReads:
    def test_get_candles_delegates_to_repository(self) -> None:
        service = _service({"market": _FakeMarketRepository([_candle()], _security())})
        candles = service.get_candles("AAPL", Timeframe.ONE_HOUR)
        assert len(candles) == 1
        assert candles[0].symbol == "AAPL"

    def test_get_security_delegates(self) -> None:
        service = _service({"market": _FakeMarketRepository([_candle()], _security())})
        assert service.get_security("AAPL", "NASDAQ").exchange == "NASDAQ"

    def test_get_compliance_status_delegates(self) -> None:
        record = ShariahCompliance(
            symbol="AAPL",
            company_name="Apple Inc.",
            exchange="NASDAQ",
            country="US",
            asset_type=AssetType.EQUITY,
            compliance_status=ComplianceStatus.COMPLIANT,
            provider="test",
            review_date=date(2026, 7, 1),
            effective_date=date(2026, 7, 1),
            screening_methodology="test",
            screening_date=date(2026, 7, 1),
        )
        service = _service({"shariah": _FakeShariahRepository(record)})
        assert service.get_compliance_status("AAPL").compliance_status is ComplianceStatus.COMPLIANT

    def test_get_fundamentals_delegates(self) -> None:
        record = CompanyFundamentals(symbol="AAPL", report_date=date(2026, 6, 30), revenue=100.0)
        service = _service({"fundamental": _FakeFundamentalRepository(record)})
        assert service.get_fundamentals("AAPL").revenue == 100.0


class TestDataServiceErrors:
    def test_get_candles_without_repository(self) -> None:
        with pytest.raises(DataNotFoundError):
            _service().get_candles("AAPL", Timeframe.ONE_HOUR)

    def test_get_security_without_repository(self) -> None:
        with pytest.raises(DataNotFoundError):
            _service().get_security("AAPL", "NASDAQ")

    def test_get_compliance_without_repository(self) -> None:
        with pytest.raises(DataNotFoundError):
            _service().get_compliance_status("AAPL")

    def test_get_fundamentals_without_repository(self) -> None:
        with pytest.raises(DataNotFoundError):
            _service().get_fundamentals("AAPL")


class TestDataServicePortfolio:
    def test_store_position_delegates(self) -> None:
        repo = _FakePortfolioRepository()
        service = _service({"portfolio": repo})
        position = PortfolioPosition(
            symbol="AAPL",
            exchange="NASDAQ",
            quantity=100.0,
            entry_price=90.0,
            current_price=100.0,
            allocation=0.4,
            sector="Technology",
        )
        stored = service.store_position(position)
        assert stored.symbol == "AAPL"
        assert service.get_position("AAPL", "NASDAQ").allocation == 0.4

    def test_list_positions_delegates(self) -> None:
        repo = _FakePortfolioRepository()
        service = _service({"portfolio": repo})
        open_position = PortfolioPosition(
            symbol="AAPL",
            exchange="NASDAQ",
            quantity=100.0,
            entry_price=90.0,
            current_price=100.0,
            allocation=0.4,
            sector="Technology",
        )
        closed_position = PortfolioPosition(
            symbol="MSFT",
            exchange="NASDAQ",
            quantity=0.0,
            entry_price=90.0,
            current_price=100.0,
            allocation=0.0,
            sector="Technology",
            status=PositionStatus.CLOSED,
        )
        service.store_position(open_position)
        service.store_position(closed_position)
        assert len(service.list_positions()) == 2
        assert len(service.list_positions(status=PositionStatus.OPEN)) == 1
        assert len(service.get_positions_by_sector("Technology")) == 1

    def test_portfolio_without_repository(self) -> None:
        with pytest.raises(DataNotFoundError):
            _service().list_positions()


class TestDataServiceDecisions:
    def test_store_and_get_decisions_delegate(self) -> None:
        repo = _FakeDecisionRepository()
        service = _service({"decision": repo})
        decision = InvestmentDecision(
            symbol="AAPL",
            decision=DecisionAction.WAIT,
            reason="aggregated analysis is incomplete",
            confidence=0.6,
            risk_score=0.4,
        )
        assert service.store_decisions([decision]) == 1
        assert len(service.get_decisions("AAPL")) == 1
        assert service.get_latest_decision("AAPL").decision is DecisionAction.WAIT

    def test_decisions_without_repository(self) -> None:
        with pytest.raises(DataNotFoundError):
            _service().get_decisions("AAPL")


class TestDataServiceIngestion:
    async def test_ingest_candles_delegates_to_pipeline(self) -> None:
        service = _service()
        run = await service.ingest_candles(
            dataset_id="ds-1",
            provider_name="test",
            fetch=lambda: [_candle()],
            store=lambda records: len(records),
        )
        assert run.records_stored == 1
