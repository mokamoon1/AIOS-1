"""Repository behavior tests (AIOS-606, AIOS-507)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    MarketStatus,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import MarketCandleModel, SecurityModel
from aios.database.repositories import (
    CompanyRepository,
    MarketRepository,
    ShariahRepository,
)

pytestmark = pytest.mark.unit


def _candle(symbol: str = "AAPL", day: int = 1) -> Candle:
    return Candle(
        timestamp=datetime(2026, 8, day, 13, 30, tzinfo=timezone.utc),
        symbol=symbol,
        timeframe=Timeframe.ONE_HOUR,
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000.0,
    )


class TestMarketRepository:
    def test_add_and_get_candles(self, session_factory) -> None:
        repo = MarketRepository(session_factory)
        stored = repo.add_candles([_candle(day=1), _candle(day=2)], provider="test")
        assert stored == 2

        candles = repo.get_candles("AAPL", Timeframe.ONE_HOUR)
        assert len(candles) == 2
        assert candles[0].timestamp.day == 1
        assert candles[1].timestamp.day == 2

    def test_duplicate_keys_not_reinserted(self, session_factory) -> None:
        repo = MarketRepository(session_factory)
        repo.add_candles([_candle(day=1)], provider="test")
        stored = repo.add_candles([_candle(day=1), _candle(day=2)], provider="test")
        assert stored == 1
        candles = repo.get_candles("AAPL", Timeframe.ONE_HOUR)
        assert len(candles) == 2

    def test_get_candles_with_range(self, session_factory) -> None:
        repo = MarketRepository(session_factory)
        repo.add_candles([_candle(day=1), _candle(day=2), _candle(day=3)], provider="test")
        candles = repo.get_candles(
            "AAPL",
            Timeframe.ONE_HOUR,
            start=datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 8, 2, 23, 59, tzinfo=timezone.utc),
        )
        assert len(candles) == 1
        assert candles[0].timestamp.day == 2

    def test_get_candles_limit(self, session_factory) -> None:
        repo = MarketRepository(session_factory)
        repo.add_candles([_candle(day=1), _candle(day=2), _candle(day=3)], provider="test")
        candles = repo.get_candles("AAPL", Timeframe.ONE_HOUR, limit=2)
        assert len(candles) == 2

    def test_get_candles_unknown_symbol(self, session_factory) -> None:
        repo = MarketRepository(session_factory)
        assert repo.get_candles("MSFT", Timeframe.ONE_HOUR) == []

    def test_add_security_idempotent(self, session_factory) -> None:
        repo = MarketRepository(session_factory)
        security = Security(
            symbol="AAPL",
            exchange="NASDAQ",
            asset_type=AssetType.EQUITY,
            currency="USD",
            trading_session="regular",
            timezone="America/New_York",
            market_status=MarketStatus.OPEN,
        )
        repo.add_security(security)
        repo.add_security(security)
        got = repo.get_security("AAPL", "NASDAQ")
        assert got.symbol == "AAPL"
        with session_factory() as session:
            count = len(session.execute(select(SecurityModel)).scalars().all())
        assert count == 1


class TestShariahRepository:
    def _record(
        self,
        symbol="AAPL",
        status=ComplianceStatus.COMPLIANT,
        effective="2026-07-01",
    ) -> ShariahCompliance:
        return ShariahCompliance(
            symbol=symbol,
            company_name="Apple Inc.",
            exchange="NASDAQ",
            country="US",
            asset_type=AssetType.EQUITY,
            compliance_status=status,
            provider="test-provider",
            review_date=date(2026, 7, 1),
            effective_date=date.fromisoformat(effective),
            screening_methodology="test-methodology",
            screening_date=date(2026, 7, 1),
        )

    def test_add_and_get_latest(self, session_factory) -> None:
        repo = ShariahRepository(session_factory)
        repo.add_records([self._record(status=ComplianceStatus.UNDER_REVIEW)])
        repo.add_records([self._record(status=ComplianceStatus.COMPLIANT)])

        latest = repo.get_compliance_status("AAPL")
        assert latest.compliance_status is ComplianceStatus.COMPLIANT

    def test_as_of_returns_effective_record(self, session_factory) -> None:
        repo = ShariahRepository(session_factory)
        earlier = self._record(status=ComplianceStatus.UNDER_REVIEW, effective="2026-06-01")
        repo.add_records([earlier])
        later = self._record(status=ComplianceStatus.COMPLIANT, effective="2026-07-01")
        repo.add_records([later])

        earlier = repo.get_compliance_status("AAPL", as_of=date(2026, 6, 15))
        assert earlier.compliance_status is ComplianceStatus.UNDER_REVIEW

    def test_unknown_symbol_raises(self, session_factory) -> None:
        repo = ShariahRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.get_compliance_status("NOPE")

    def test_add_empty(self, session_factory) -> None:
        repo = ShariahRepository(session_factory)
        assert repo.add_records([]) == 0


class TestCompanyRepository:
    def _record(self, revenue=100.0) -> CompanyFundamentals:
        return CompanyFundamentals(
            symbol="AAPL",
            revenue=revenue,
            report_date=date(2026, 6, 30),
        )

    def test_add_and_get_latest(self, session_factory) -> None:
        repo = CompanyRepository(session_factory)
        repo.add_fundamentals([self._record(revenue=90.0)])
        repo.add_fundamentals([self._record(revenue=100.0)])

        latest = repo.get_fundamentals("AAPL")
        assert latest.revenue == 100.0

    def test_get_by_report_date(self, session_factory) -> None:
        repo = CompanyRepository(session_factory)
        repo.add_fundamentals([self._record()])
        got = repo.get_fundamentals("AAPL", report_date=date(2026, 6, 30))
        assert got.revenue == 100.0

    def test_unknown_symbol_raises(self, session_factory) -> None:
        repo = CompanyRepository(session_factory)
        with pytest.raises(RecordNotFoundError):
            repo.get_fundamentals("NOPE")


class TestRepositoryProtocolConformance:
    def test_market_repository_implements_protocol(self, session_factory) -> None:
        from aios.database.repository import Repository

        repo = MarketRepository(session_factory)
        assert isinstance(repo, Repository)

    def test_generic_add_get_delete(self, session_factory) -> None:
        repo = MarketRepository(session_factory)
        candle = _candle()
        with session_factory() as session:
            model = MarketCandleModel(
                timestamp=candle.timestamp,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                provider="test",
            )
            repo.add(session, model)
            session.commit()
            entity_id = model.id
            found = repo.get(session, entity_id)
            assert found is not None
            listed = repo.list(session)
            assert len(listed) == 1
            iterated = list(repo.iterator(session))
            assert len(iterated) == 1
            repo.delete(session, entity_id)
            session.commit()
            assert repo.get(session, entity_id) is None
