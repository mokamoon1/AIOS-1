"""Standard data model tests (AIOS-503, AIOS-504, AIOS-502)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    MarketStatus,
    Security,
    SessionStatus,
    ShariahCompliance,
    Timeframe,
)

pytestmark = pytest.mark.unit


def _valid_candle(**overrides) -> dict:
    base = {
        "timestamp": "2026-08-01T13:30:00Z",
        "symbol": "AAPL",
        "timeframe": "1h",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 1000.0,
    }
    base.update(overrides)
    return base


class TestCandleModel:
    def test_valid_candle_constructs(self) -> None:
        candle = Candle.model_validate(_valid_candle())
        assert candle.symbol == "AAPL"
        assert candle.timeframe is Timeframe.ONE_HOUR
        assert candle.open == 100.0

    def test_open_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Candle.model_validate(_valid_candle(open=0.0))

    def test_volume_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            Candle.model_validate(_valid_candle(volume=-1))

    def test_trade_count_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            Candle.model_validate(_valid_candle(trade_count=-2))

    def test_timeframe_is_enum(self) -> None:
        candle = Candle.model_validate(_valid_candle(timeframe="4h"))
        assert candle.timeframe is Timeframe.FOUR_HOURS

    def test_symbol_must_not_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            Candle.model_validate(_valid_candle(symbol="   "))

    def test_models_are_frozen(self) -> None:
        candle = Candle.model_validate(_valid_candle())
        with pytest.raises(ValidationError):
            candle.close = 1.0  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Candle.model_validate(_valid_candle(unexpected="value"))

    def test_optional_fields(self) -> None:
        candle = Candle.model_validate(_valid_candle(vwap=101.5, trade_count=42))
        assert candle.vwap == 101.5
        assert candle.trade_count == 42

    def test_all_timeframes_defined(self) -> None:
        values = {tf.value for tf in Timeframe}
        assert values == {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"}


class TestSecurityModel:
    def test_valid_security(self) -> None:
        security = Security(
            symbol="AAPL",
            exchange="NASDAQ",
            asset_type=AssetType.EQUITY,
            currency="USD",
            trading_session="regular",
            timezone="America/New_York",
            market_status=MarketStatus.OPEN,
        )
        assert security.asset_type is AssetType.EQUITY

    def test_empty_symbol_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Security(
                symbol="",
                exchange="NASDAQ",
                asset_type=AssetType.EQUITY,
                currency="USD",
                trading_session="regular",
                timezone="America/New_York",
                market_status=MarketStatus.OPEN,
            )

    def test_unsupported_asset_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Security.model_validate(
                {
                    "symbol": "AAPL",
                    "exchange": "NASDAQ",
                    "asset_type": "crypto",
                    "currency": "USD",
                    "trading_session": "regular",
                    "timezone": "America/New_York",
                    "market_status": "open",
                }
            )


class TestShariahComplianceModel:
    def _valid(self, **overrides) -> dict:
        base = {
            "symbol": "AAPL",
            "company_name": "Apple Inc.",
            "exchange": "NASDAQ",
            "country": "US",
            "asset_type": "equity",
            "compliance_status": "compliant",
            "provider": "test-provider",
            "review_date": "2026-07-01",
            "effective_date": "2026-07-01",
            "screening_methodology": "test-methodology",
            "screening_date": "2026-07-01",
        }
        base.update(overrides)
        return base

    def test_valid_record(self) -> None:
        record = ShariahCompliance.model_validate(self._valid())
        assert record.compliance_status is ComplianceStatus.COMPLIANT

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ShariahCompliance.model_validate(self._valid(confidence_level=1.5))

    def test_status_values(self) -> None:
        for status in ("compliant", "non_compliant", "under_review", "unknown"):
            record = ShariahCompliance.model_validate(self._valid(compliance_status=status))
            assert record.compliance_status.value == status

    def test_unknown_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ShariahCompliance.model_validate(self._valid(compliance_status="halal"))

    def test_default_confidence_is_one(self) -> None:
        record = ShariahCompliance.model_validate(self._valid())
        assert record.confidence_level == 1.0


class TestCompanyFundamentalsModel:
    def _valid(self, **overrides) -> dict:
        base = {
            "symbol": "AAPL",
            "report_date": "2026-06-30",
            "revenue": 100_000.0,
            "net_income": 20_000.0,
        }
        base.update(overrides)
        return base

    def test_valid_fundamentals(self) -> None:
        record = CompanyFundamentals.model_validate(self._valid())
        assert record.symbol == "AAPL"
        assert record.revenue == 100_000.0

    def test_report_date_required(self) -> None:
        data = self._valid()
        del data["report_date"]
        with pytest.raises(ValidationError):
            CompanyFundamentals.model_validate(data)

    def test_optional_financials_allow_none(self) -> None:
        record = CompanyFundamentals.model_validate(self._valid(eps=None, assets=None))
        assert record.eps is None


class TestEnums:
    def test_asset_type_equity_only(self) -> None:
        assert [item.value for item in AssetType] == ["equity"]

    def test_market_status_values(self) -> None:
        assert {s.value for s in MarketStatus} == {"open", "closed", "halted", "suspended"}

    def test_session_status_values(self) -> None:
        assert {s.value for s in SessionStatus} == {
            "pre_market",
            "regular",
            "after_hours",
            "closed",
        }
