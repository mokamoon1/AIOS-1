"""ORM model mapping tests (ADR-0006, AIOS-402)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from aios.data.models import (
    AssetType,
    ComplianceStatus,
    MarketStatus,
    Timeframe,
)
from aios.database.models import (
    CompanyFundamentalModel,
    EventLogModel,
    MarketCandleModel,
    SecurityModel,
    ShariahSecurityModel,
)
from aios.events.event import Event, EventPriority, EventStatus

pytestmark = pytest.mark.unit


class TestMarketCandleModel:
    def test_roundtrip_to_domain(self, session_factory) -> None:
        row = MarketCandleModel(
            timestamp=datetime(2026, 8, 1, 13, 30, tzinfo=timezone.utc),
            symbol="AAPL",
            timeframe=Timeframe.ONE_HOUR,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
            provider="test",
        )
        with session_factory() as session:
            session.add(row)
            session.commit()
            stored = session.execute(
                select(MarketCandleModel).where(MarketCandleModel.symbol == "AAPL")
            ).scalar_one()

        candle = stored.to_domain()
        assert candle.symbol == "AAPL"
        assert candle.timeframe is Timeframe.ONE_HOUR
        assert candle.timestamp.tzinfo is not None
        assert candle.close == 104.0

    def test_table_names_are_snake_case(self) -> None:
        assert MarketCandleModel.__tablename__ == "market_candles"
        assert SecurityModel.__tablename__ == "securities"
        assert ShariahSecurityModel.__tablename__ == "shariah_securities"
        assert CompanyFundamentalModel.__tablename__ == "company_fundamentals"
        assert EventLogModel.__tablename__ == "event_logs"

    def test_primary_key_named_id(self) -> None:
        for model in (
            MarketCandleModel,
            SecurityModel,
            ShariahSecurityModel,
            CompanyFundamentalModel,
            EventLogModel,
        ):
            assert model.__table__.primary_key.columns.keys() == ["id"]


class TestSecurityModelMapping:
    def test_roundtrip_to_domain(self, session_factory) -> None:
        row = SecurityModel(
            symbol="AAPL",
            exchange="NASDAQ",
            asset_type=AssetType.EQUITY,
            currency="USD",
            trading_session="regular",
            timezone="America/New_York",
            market_status=MarketStatus.OPEN,
        )
        with session_factory() as session:
            session.add(row)
            session.commit()
            stored = session.execute(select(SecurityModel)).scalar_one()

        security = stored.to_domain()
        assert security.symbol == "AAPL"
        assert security.market_status is MarketStatus.OPEN


class TestShariahSecurityModelMapping:
    def test_roundtrip_to_domain(self, session_factory) -> None:
        row = ShariahSecurityModel(
            symbol="AAPL",
            company_name="Apple Inc.",
            exchange="NASDAQ",
            country="US",
            asset_type=AssetType.EQUITY,
            compliance_status=ComplianceStatus.COMPLIANT,
            provider="test-provider",
            provider_version="1.0.0",
            review_date=date(2026, 7, 1),
            effective_date=date(2026, 7, 1),
            screening_methodology="test-methodology",
            screening_version="1.0.0",
            screening_date=date(2026, 7, 1),
            confidence_level=0.9,
            retrieval_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        with session_factory() as session:
            session.add(row)
            session.commit()
            stored = session.execute(select(ShariahSecurityModel)).scalar_one()

        record = stored.to_domain()
        assert record.compliance_status is ComplianceStatus.COMPLIANT
        assert record.confidence_level == 0.9


class TestCompanyFundamentalModelMapping:
    def test_roundtrip_to_domain(self, session_factory) -> None:
        row = CompanyFundamentalModel(
            symbol="AAPL",
            revenue=100.0,
            net_income=20.0,
            report_date=date(2026, 6, 30),
            retrieval_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        with session_factory() as session:
            session.add(row)
            session.commit()
            stored = session.execute(select(CompanyFundamentalModel)).scalar_one()

        record = stored.to_domain()
        assert record.symbol == "AAPL"
        assert record.revenue == 100.0
        assert record.report_date == date(2026, 6, 30)


class TestEventLogModelMapping:
    def test_from_event_and_roundtrip(self, session_factory) -> None:
        event = Event(
            event_id=uuid4(),
            source="test",
            event_type="MARKET_DATA_UPDATED",
            payload={"symbol": "AAPL"},
            priority=EventPriority.HIGH,
            status=EventStatus.CREATED,
        )
        row = EventLogModel.from_event(event)
        with session_factory() as session:
            session.add(row)
            session.commit()
            stored = session.execute(
                select(EventLogModel).where(EventLogModel.event_id == event.event_id)
            ).scalar_one()

        restored = stored.to_domain()
        assert restored.event_id == event.event_id
        assert restored.event_type == "MARKET_DATA_UPDATED"
        assert restored.payload == {"symbol": "AAPL"}
        assert restored.priority is EventPriority.HIGH
        assert restored.status is EventStatus.CREATED
