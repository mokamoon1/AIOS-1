"""SQLAlchemy ORM models (ADR-0006, AIOS-402, AIOS-503, AIOS-504).

Tables follow snake_case naming with a primary key ``id`` and foreign keys
named ``<entity>_id`` per AIOS-1103 and ADR-0006 section 5.3. Enum columns
store the documented string values (AIOS-503 section 12, AIOS-504 section 6)
using portable VARCHAR columns so the schema works on both PostgreSQL and
the SQLite test database (ADR-0001, ADR-0006 section 5.2).

Historical records are immutable: repositories append new rows instead of
overwriting existing ones (AIOS-505, AIOS-507).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    from aios.analysis.models import AnalysisResult
    from aios.analysis.news import NewsArticle, SentimentEvaluation, SentimentLabel
from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
)
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
from aios.database.base import Base
from aios.events.event import Event, EventPriority, EventStatus


def _utc(value: datetime) -> datetime:
    """Normalize a database datetime to a UTC-aware datetime.

    SQLite returns naive datetimes regardless of the declared column type;
    domain models require UTC timestamps, so an explicit UTC time zone is
    attached here to keep round trips consistent.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


def _sa_enum(enum_cls: type[Enum], name: str) -> SqlEnum:
    """Portable string-backed SQLAlchemy enum (native_enum=False).

    Uses the documented string values so PostgreSQL and SQLite remain
    schema compatible (ADR-0001, ADR-0006 section 5.2).
    """
    return SqlEnum(
        enum_cls,
        name=name,
        values_callable=_enum_values,
        native_enum=False,
        validate_strings=True,
    )


class SecurityModel(Base):
    """Core security entity (AIOS-503 section 4, ADR-0006 section 5.5)."""

    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(_sa_enum(AssetType, "asset_type"), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    trading_session: Mapped[str] = mapped_column(String(32), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    market_status: Mapped[MarketStatus] = mapped_column(
        _sa_enum(MarketStatus, "market_status"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_securities_symbol_exchange"),)

    def to_domain(self) -> Security:
        """Return the AIOS security domain model (AIOS-503 section 4)."""
        return Security(
            symbol=self.symbol,
            exchange=self.exchange,
            asset_type=self.asset_type,
            currency=self.currency,
            trading_session=self.trading_session,
            timezone=self.timezone,
            market_status=self.market_status,
        )


class MarketCandleModel(Base):
    """Historical candle record (AIOS-503 section 5, ADR-0006 section 5.5).

    Immutable historical record: rows are appended, never overwritten.
    Uniqueness over (symbol, timeframe, timestamp) prevents duplicate
    ingestion and satisfies the lookups defined in AIOS-507.
    """

    __tablename__ = "market_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[Timeframe] = mapped_column(_sa_enum(Timeframe, "timeframe"), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    vwap: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "timestamp", name="uq_market_candles_symbol_timeframe_timestamp"
        ),
        Index("ix_market_candles_symbol_timeframe", "symbol", "timeframe"),
    )

    def to_domain(self) -> Candle:
        """Return the AIOS candle domain model (AIOS-503 section 5)."""
        return Candle(
            timestamp=_utc(self.timestamp),
            symbol=self.symbol,
            timeframe=self.timeframe,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            vwap=self.vwap,
            trade_count=self.trade_count,
            average_price=self.average_price,
        )


class ShariahSecurityModel(Base):
    """Shariah compliance record (AIOS-504, ADR-0006 section 5.4).

    Every provider review creates a new record; compliance history is never
    overwritten (AIOS-504 section 9).
    """

    __tablename__ = "shariah_securities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(_sa_enum(AssetType, "asset_type"), nullable=False)
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        _sa_enum(ComplianceStatus, "compliance_status"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(32), nullable=False)
    review_date: Mapped[date] = mapped_column(nullable=False)
    effective_date: Mapped[date] = mapped_column(nullable=False)
    expiration_date: Mapped[date | None] = mapped_column(nullable=True)
    screening_methodology: Mapped[str] = mapped_column(String(255), nullable=False)
    screening_version: Mapped[str] = mapped_column(String(32), nullable=False)
    screening_date: Mapped[date] = mapped_column(nullable=False)
    confidence_level: Mapped[float] = mapped_column(Float, nullable=False)
    previous_status: Mapped[ComplianceStatus | None] = mapped_column(
        _sa_enum(ComplianceStatus, "previous_status"), nullable=True
    )
    retrieval_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (Index("ix_shariah_securities_symbol_effective", "symbol", "effective_date"),)

    def to_domain(self) -> ShariahCompliance:
        """Return the AIOS compliance domain model (AIOS-504)."""
        return ShariahCompliance(
            symbol=self.symbol,
            company_name=self.company_name,
            exchange=self.exchange,
            country=self.country,
            asset_type=self.asset_type,
            compliance_status=self.compliance_status,
            provider=self.provider,
            provider_version=self.provider_version,
            review_date=self.review_date,
            effective_date=self.effective_date,
            expiration_date=self.expiration_date,
            screening_methodology=self.screening_methodology,
            screening_version=self.screening_version,
            screening_date=self.screening_date,
            confidence_level=self.confidence_level,
            previous_status=self.previous_status,
            retrieval_timestamp=_utc(self.retrieval_timestamp),
        )


class CompanyFundamentalModel(Base):
    """Company financial information (AIOS-502 section 6, AIOS-402 section 6)."""

    __tablename__ = "company_fundamentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    sector: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    industry: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_date: Mapped[date] = mapped_column(nullable=False)
    retrieval_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (Index("ix_company_fundamentals_symbol_report", "symbol", "report_date"),)

    def to_domain(self) -> CompanyFundamentals:
        """Return the AIOS fundamentals domain model (AIOS-502 section 6)."""
        return CompanyFundamentals(
            symbol=self.symbol,
            sector=self.sector,
            industry=self.industry,
            revenue=self.revenue,
            net_income=self.net_income,
            eps=self.eps,
            assets=self.assets,
            liabilities=self.liabilities,
            cash_flow=self.cash_flow,
            equity=self.equity,
            report_date=self.report_date,
            retrieval_timestamp=_utc(self.retrieval_timestamp),
        )


class AnalysisResultModel(Base):
    """Analysis result record (AIOS-402 ``analysis_results``, ADR-0006).

    Stores AIOS analysis outputs: the symbol, the analysis type that produced
    the result, the analyzed timeframe, the resulting score and short result
    label, and the full detail payload. Historical records are immutable:
    rows are appended, never overwritten (AIOS-505, AIOS-507). Uniqueness
    over (symbol, analysis_type, timeframe, analyzed_at) prevents duplicate
    storage of the same analysis run.
    """

    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[Timeframe] = mapped_column(_sa_enum(Timeframe, "timeframe"), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "analysis_type",
            "timeframe",
            "analyzed_at",
            name="uq_analysis_results_symbol_type_timeframe_analyzed_at",
        ),
        Index("ix_analysis_results_symbol_timeframe", "symbol", "timeframe"),
    )

    @classmethod
    def from_result(cls, result: AnalysisResult) -> AnalysisResultModel:
        """Create an analysis result row from the domain model (AIOS-402)."""
        return cls(
            symbol=result.symbol,
            analysis_type=result.analysis_type,
            timeframe=result.timeframe,
            score=result.score,
            result=result.result,
            details=dict(result.details),
            analyzed_at=result.analyzed_at,
        )

    def to_domain(self) -> AnalysisResult:
        """Return the AIOS analysis result domain model (AIOS-402)."""
        from aios.analysis.models import AnalysisResult
        return AnalysisResult(
            symbol=self.symbol,
            analysis_type=self.analysis_type,
            timeframe=self.timeframe,
            score=self.score,
            result=self.result,
            details=dict(self.details),
            analyzed_at=_utc(self.analyzed_at),
        )


class PortfolioPositionModel(Base):
    """Portfolio position record (AIOS-402 ``portfolio_positions``, ADR-0006).

    Tracks current holdings per AIOS-402 section 8: the symbol, quantity,
    entry price, current price, allocation (fraction of portfolio value),
    status, and sector. The current-position view is updated in place when a
    holding changes; ``updated_at`` records the last allocation change
    (AIOS-206 section 8). Position history and performance tracking are
    future phase scope (AIOS-501 section 5.4, AIOS-402 section 15).
    """

    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    allocation: Mapped[float] = mapped_column(Float, nullable=False)
    sector: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[PositionStatus] = mapped_column(
        _sa_enum(PositionStatus, "position_status"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("symbol", "exchange", name="uq_portfolio_positions_symbol_exchange"),
    )

    @classmethod
    def from_position(cls, position: PortfolioPosition) -> PortfolioPositionModel:
        """Create a portfolio position row from the domain model (AIOS-402)."""
        return cls(
            symbol=position.symbol,
            exchange=position.exchange,
            quantity=position.quantity,
            entry_price=position.entry_price,
            current_price=position.current_price,
            allocation=position.allocation,
            sector=position.sector,
            status=position.status,
            updated_at=position.updated_at,
        )

    def to_domain(self) -> PortfolioPosition:
        """Return the AIOS portfolio position domain model (AIOS-402)."""
        return PortfolioPosition(
            symbol=self.symbol,
            exchange=self.exchange,
            quantity=self.quantity,
            entry_price=self.entry_price,
            current_price=self.current_price,
            allocation=self.allocation,
            sector=self.sector,
            status=self.status,
            updated_at=_utc(self.updated_at),
        )


class InvestmentDecisionModel(Base):
    """Investment decision record (AIOS-402 ``investment_decisions``, ADR-0006).

    Stores the documented decision fields (AIOS-402 section 9): symbol,
    decision direction, reason, confidence, risk score, and timestamp.
    Decision history is immutable: rows are appended, never overwritten
    (AIOS-208 section 11, AIOS-505, AIOS-507). The full explanation payload
    from AIOS-208 section 7 is preserved in ``supporting_data``.
    """

    __tablename__ = "investment_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[DecisionAction] = mapped_column(
        _sa_enum(DecisionAction, "decision_action"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(1024), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supporting_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (Index("ix_investment_decisions_symbol_timestamp", "symbol", "timestamp"),)

    @classmethod
    def from_decision(cls, decision: InvestmentDecision) -> InvestmentDecisionModel:
        """Create an investment decision row from the domain model (AIOS-402)."""
        return cls(
            symbol=decision.symbol,
            decision=decision.decision,
            reason=decision.reason,
            confidence=decision.confidence,
            risk_score=decision.risk_score,
            timestamp=decision.timestamp,
            supporting_data=dict(decision.supporting_data),
        )

    def to_domain(self) -> InvestmentDecision:
        """Return the AIOS investment decision domain model (AIOS-402)."""
        return InvestmentDecision(
            symbol=self.symbol,
            decision=self.decision,
            reason=self.reason,
            confidence=self.confidence,
            risk_score=self.risk_score,
            timestamp=_utc(self.timestamp),
            supporting_data=dict(self.supporting_data),
        )


class PaperOrderModel(Base):
    """Paper order record (AIOS-407 section 4.3, ADR-0006).

    Stores the paper order book. Orders are updated in place only for the
    documented lifecycle transitions; fills are appended immutably so the
    execution history is preserved (AIOS-101 section 4.6, AIOS-402 section
    11, AIOS-1103 section 11).
    """

    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    broker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[OrderSide] = mapped_column(_sa_enum(OrderSide, "order_side"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        _sa_enum(OrderStatus, "order_status"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    decision_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_paper_orders_symbol_status", "symbol", "status"),
        Index("ix_paper_orders_broker_submitted", "broker_id", "submitted_at"),
    )

    @classmethod
    def from_order(cls, order: PaperOrder) -> PaperOrderModel:
        """Create a paper order row from the domain model (AIOS-407)."""
        return cls(
            order_id=order.order_id,
            broker_id=order.broker_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            status=order.status,
            reason=order.reason,
            decision_ref=order.decision_ref,
            submitted_at=order.submitted_at,
            updated_at=order.updated_at,
        )

    def to_domain(self) -> PaperOrder:
        """Return the broker paper order domain model (AIOS-407)."""
        return PaperOrder(
            order_id=self.order_id,
            broker_id=self.broker_id,
            symbol=self.symbol,
            exchange=self.exchange,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            status=self.status,
            reason=self.reason,
            decision_ref=self.decision_ref,
            submitted_at=_utc(self.submitted_at),
            updated_at=_utc(self.updated_at),
        )


class PaperFillModel(Base):
    """Paper fill record (AIOS-101 section 4.6, ADR-0006).

    Fills are immutable historical records appended for every explicit fill;
    they are never overwritten (AIOS-402 section 11). ``realized_pnl`` is the
    objective arithmetic realized profit/loss recorded at fill time.
    """

    __tablename__ = "paper_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fill_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[OrderSide] = mapped_column(_sa_enum(OrderSide, "order_side"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (Index("ix_paper_fills_order_id", "order_id"),)

    @classmethod
    def from_fill(cls, fill: PaperFill) -> PaperFillModel:
        """Create a paper fill row from the domain model (AIOS-101 section 4.6)."""
        return cls(
            fill_id=fill.fill_id,
            order_id=fill.order_id,
            broker_id=fill.broker_id,
            symbol=fill.symbol,
            exchange=fill.exchange,
            side=fill.side,
            quantity=fill.quantity,
            price=fill.price,
            realized_pnl=fill.realized_pnl,
            filled_at=fill.filled_at,
        )

    def to_domain(self) -> PaperFill:
        """Return the broker paper fill domain model (AIOS-101 section 4.6)."""
        return PaperFill(
            fill_id=self.fill_id,
            order_id=self.order_id,
            broker_id=self.broker_id,
            symbol=self.symbol,
            exchange=self.exchange,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            realized_pnl=self.realized_pnl,
            filled_at=_utc(self.filled_at),
        )


class PaperPositionModel(Base):
    """Paper position record (AIOS-407 section 4.3, ADR-0006).

    The current broker-side holdings view, updated in place after each fill
    (AIOS-603 section 11). Values are objective arithmetic on recorded fills.
    """

    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    market_value: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("symbol", "exchange", name="uq_paper_positions_symbol_exchange"),
    )

    @classmethod
    def from_position(cls, position: BrokerPosition) -> PaperPositionModel:
        """Create a paper position row from the domain model (AIOS-407)."""
        return cls(
            symbol=position.symbol,
            exchange=position.exchange,
            quantity=position.quantity,
            entry_price=position.entry_price,
            current_price=position.current_price,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            updated_at=position.updated_at,
        )

    def to_domain(self) -> BrokerPosition:
        """Return the broker position domain model (AIOS-407)."""
        return BrokerPosition(
            symbol=self.symbol,
            exchange=self.exchange,
            quantity=self.quantity,
            entry_price=self.entry_price,
            current_price=self.current_price,
            market_value=self.market_value,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
            updated_at=_utc(self.updated_at),
        )


class BrokerAccountModel(Base):
    """Broker account record (AIOS-407 section 4.3 "Check Account", ADR-0006).

    Stores the current paper account status. ``initial_cash`` is the
    configurable starting paper capital placeholder.
    """

    __tablename__ = "broker_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    initial_cash: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    @classmethod
    def from_account(cls, account: BrokerAccount) -> BrokerAccountModel:
        """Create a broker account row from the domain model (AIOS-407)."""
        return cls(
            broker_id=account.broker_id,
            account_id=account.account_id,
            currency=account.currency,
            cash=account.cash,
            initial_cash=account.initial_cash,
            updated_at=account.updated_at,
        )

    def to_domain(self) -> BrokerAccount:
        """Return the broker account domain model (AIOS-407)."""
        return BrokerAccount(
            broker_id=self.broker_id,
            account_id=self.account_id,
            currency=self.currency,
            cash=self.cash,
            initial_cash=self.initial_cash,
            updated_at=_utc(self.updated_at),
        )


def to_domain(self) -> Event:
        """Return the AIOS event domain model (AIOS-103)."""
        return Event(
            event_id=self.event_id,
            timestamp=_utc(self.timestamp),
            source=self.source,
            event_type=self.event_type,
            payload=dict(self.payload),
            priority=EventPriority(self.priority),
            status=EventStatus(self.status),
        )


class NewsArticleModel(Base):
    """News article record (Phase 9.1).

    Stores standardized news articles from providers. Historical records
    are immutable: rows are appended and never overwritten.
    """

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    article_id: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "provider", "article_id", name="uq_news_articles_provider_article_id"
        ),
        Index("ix_news_articles_symbols", "symbols"),
        Index("ix_news_articles_published_at", "published_at"),
    )

    def to_domain(self) -> NewsArticle:
        """Return the AIOS news article domain model."""
        return NewsArticle(
            provider=self.provider,
            article_id=self.article_id,
            published_at=_utc(self.published_at),
            retrieved_at=_utc(self.retrieved_at),
            source=self.source,
            headline=self.headline,
            summary=self.summary,
            url=self.url,
            symbols=self.symbols,
        )


class NewsSentimentModel(Base):
    """News sentiment evaluation record (Phase 9.1).

    Stores sentiment evaluations for news articles. Historical records
    are immutable: rows are appended and never overwritten.
    """

    __tablename__ = "news_sentiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    article_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    methodology: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_news_sentiments_article_id", "article_id"),
        Index("ix_news_sentiments_evaluated_at", "evaluated_at"),
    )

    def to_domain(self) -> SentimentEvaluation:
        """Return the AIOS sentiment evaluation domain model."""
        from aios.analysis.news import SentimentLabel
        return SentimentEvaluation(
            provider=self.provider,
            article_id=self.article_id,
            sentiment=SentimentLabel(self.sentiment),
            score=self.score,
            methodology=self.methodology,
            evaluated_at=_utc(self.evaluated_at),
        )


class EventLogModel(Base):
    """Event log storage (ADR-0005 section 5.5, ADR-0006 section 5.6).

    Stores the full AIOS-103 event structure in snake_case columns. Events
    are persisted before dispatch (save-before-publish) and never deleted.
    """

    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_event_logs_timestamp", "timestamp"),
        Index("ix_event_logs_source_type", "source", "event_type"),
    )

    @classmethod
    def from_event(cls, event: Event) -> EventLogModel:
        """Create an event log row from an AIOS event (ADR-0005 section 5.5)."""
        return cls(
            event_id=event.event_id,
            timestamp=event.timestamp,
            source=event.source,
            event_type=event.event_type,
            payload=dict(event.payload),
            priority=event.priority.value,
            status=event.status.value,
        )

    def to_domain(self) -> Event:
        """Return the AIOS event domain model (AIOS-103)."""
        return Event(
            event_id=self.event_id,
            timestamp=_utc(self.timestamp),
            source=self.source,
            event_type=self.event_type,
            payload=dict(self.payload),
            priority=EventPriority(self.priority),
            status=EventStatus(self.status),
        )


# =============================================================================
# Backtest Models (Phase 9.5)
# =============================================================================

class BacktestRunModel(Base):
    """Persistent backtest run record."""

    __tablename__ = "backtest_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_backtest_runs_started_at", "started_at"),
        Index("ix_backtest_runs_status", "status"),
    )


class BacktestEquityPointModel(Base):
    """Equity curve point for a backtest run."""

    __tablename__ = "backtest_equity_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("backtest_runs.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    market_value: Mapped[float] = mapped_column(Float, nullable=False)
    daily_return: Mapped[float] = mapped_column(Float, nullable=False)
    cumulative_return: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("run_id", "timestamp", name="uq_backtest_equity_run_timestamp"),
        Index("ix_backtest_equity_points_run_timestamp", "run_id", "timestamp"),
    )
