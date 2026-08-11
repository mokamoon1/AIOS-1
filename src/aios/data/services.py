"""Internal Data Services facade (AIOS-501 section 2).

The Data Layer is the single entry point for all market, Shariah, and
fundamental data. Analysis and decision engines must not access providers
directly; they consume data through this facade, which routes queries to the
Database Layer repositories and ingestion to the Data Pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

from aios.analysis.news import NewsArticle, SentimentEvaluation
from aios.brokers.models import (
    BrokerAccount,
    BrokerPosition,
    OrderStatus,
    PaperFill,
    PaperOrder,
)
from aios.data.exceptions import DataNotFoundError
from aios.data.models import (
    Candle,
    CompanyFundamentals,
    InvestmentDecision,
    PortfolioPosition,
    PositionStatus,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.data.pipeline import DataPipeline, PipelineRun


class MarketDataRepository(Protocol):
    """Read interface implemented by the Database Layer market repository."""

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[Candle]: ...

    def get_security(self, symbol: str, exchange: str) -> Security: ...


class ShariahDataRepository(Protocol):
    """Read interface implemented by the Database Layer Shariah repository."""

    def get_compliance_status(
        self, symbol: str, *, as_of: date | None = None
    ) -> ShariahCompliance: ...


class FundamentalDataRepository(Protocol):
    """Read interface implemented by the Database Layer company repository."""

    def get_fundamentals(
        self, symbol: str, *, report_date: date | None = None
    ) -> CompanyFundamentals: ...


class PortfolioDataRepository(Protocol):
    """Read/write interface implemented by the Database Layer portfolio repository.

    The current-holdings view is owned by the Portfolio Module (AIOS-501
    section 7) and is written through this facade; position history is
    preserved by the Database Layer (AIOS-402 section 11).
    """

    def upsert_position(self, position: PortfolioPosition) -> PortfolioPosition: ...

    def get_position(self, symbol: str, exchange: str) -> PortfolioPosition: ...

    def list_positions(
        self, *, status: PositionStatus | None = None
    ) -> list[PortfolioPosition]: ...

    def get_positions_by_sector(self, sector: str) -> list[PortfolioPosition]: ...


class DecisionDataRepository(Protocol):
    """Read/write interface implemented by the Database Layer decision repository.

    Decision history is immutable and owned by the Decision Engine (AIOS-501
    section 7); records are appended through this facade (AIOS-208 section 11).
    """

    def add_decisions(self, decisions: list[InvestmentDecision]) -> int: ...

    def get_decisions(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[InvestmentDecision]: ...

    def get_latest_decision(self, symbol: str) -> InvestmentDecision: ...


class NewsDataRepository(Protocol):
    """Read/write interface implemented by the Database Layer news repository.

    News articles and sentiment evaluations are stored and retrieved through
    this facade (Phase 9.1).
    """

    def get_articles(
        self,
        symbol: str | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsArticle]: ...

    def get_sentiment(self, article_id: str) -> SentimentEvaluation | None: ...

    def get_sentiment_history(
        self, article_id: str, *, since: datetime | None = None
    ) -> list[SentimentEvaluation]: ...


class PaperOrderDataRepository(Protocol):
    """Read/write interface implemented by the Database Layer paper order repository.

    Paper orders flow through this facade so the Broker module never touches
    the database directly (AIOS-606 section 1, AIOS-605 section 13).
    """

    def add_order(self, order: PaperOrder) -> PaperOrder: ...

    def get_order(self, order_id: str) -> PaperOrder: ...

    def list_orders(self, *, status: OrderStatus | None = None) -> list[PaperOrder]: ...

    def update_order(self, order: PaperOrder) -> PaperOrder: ...


class PaperFillDataRepository(Protocol):
    """Append-only interface for recorded paper fills (AIOS-101 section 4.6)."""

    def add_fill(self, fill: PaperFill) -> PaperFill: ...

    def list_fills(self, *, order_id: str | None = None) -> list[PaperFill]: ...


class PaperPositionDataRepository(Protocol):
    """Read/write interface for the broker-side paper positions view."""

    def upsert_position(self, position: BrokerPosition) -> BrokerPosition: ...

    def list_positions(self) -> list[BrokerPosition]: ...


class BrokerAccountDataRepository(Protocol):
    """Read/write interface for the paper broker account (AIOS-407)."""

    def upsert_account(self, account: BrokerAccount) -> BrokerAccount: ...

    def get_account(self, broker_id: str) -> BrokerAccount: ...


class DataService:
    """Facade over Data Layer read and ingest operations (AIOS-501).

    Read operations delegate to injected Database Layer repositories so this
    facade never touches the database directly (AIOS-606 section 1). No
    module outside the Data Layer accesses providers; ingestion is delegated
    to the injected :class:`DataPipeline`.
    """

    def __init__(
        self,
        pipeline: DataPipeline,
        *,
        market_repository: MarketDataRepository | None = None,
        shariah_repository: ShariahDataRepository | None = None,
        fundamental_repository: FundamentalDataRepository | None = None,
        news_repository: NewsDataRepository | None = None,
        portfolio_repository: PortfolioDataRepository | None = None,
        decision_repository: DecisionDataRepository | None = None,
        paper_order_repository: PaperOrderDataRepository | None = None,
        paper_fill_repository: PaperFillDataRepository | None = None,
        paper_position_repository: PaperPositionDataRepository | None = None,
        broker_account_repository: BrokerAccountDataRepository | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._market = market_repository
        self._shariah = shariah_repository
        self._fundamental = fundamental_repository
        self._news = news_repository
        self._portfolio = portfolio_repository
        self._decision = decision_repository
        self._paper_order = paper_order_repository
        self._paper_fill = paper_fill_repository
        self._paper_position = paper_position_repository
        self._broker_account = broker_account_repository
        self._logger = logger or logging.getLogger("aios.data.services")

    # -- ingestion --------------------------------------------------------

    async def ingest_candles(
        self,
        *,
        dataset_id: str,
        provider_name: str,
        fetch,
        store,
        quarantine_on_warning: bool = False,
    ) -> PipelineRun:
        """Acquire, validate, normalize, and store a candle dataset."""
        return await self._pipeline.ingest_candles(
            dataset_id=dataset_id,
            provider_name=provider_name,
            fetch=fetch,
            store=store,
            quarantine_on_warning=quarantine_on_warning,
        )

    # -- market data queries -----------------------------------------------

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[Candle]:
        """Return candles for ``symbol`` and ``timeframe``.

        Requires a market repository; raises :class:`DataNotFoundError` when
        the repository is not configured.
        """
        if self._market is None:
            raise DataNotFoundError("No market repository configured")
        return self._market.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
        )

    def get_security(self, symbol: str, exchange: str) -> Security:
        """Return the security entity for ``symbol``/``exchange``."""
        if self._market is None:
            raise DataNotFoundError("No market repository configured")
        return self._market.get_security(symbol=symbol, exchange=exchange)

    # -- Shariah data queries ----------------------------------------------

    def get_compliance_status(self, symbol: str, *, as_of: date | None = None) -> ShariahCompliance:
        """Return the latest compliance record for ``symbol``."""
        if self._shariah is None:
            raise DataNotFoundError("No Shariah repository configured")
        return self._shariah.get_compliance_status(symbol=symbol, as_of=as_of)

    # -- fundamental data queries ------------------------------------------

    def get_fundamentals(
        self, symbol: str, *, report_date: date | None = None
    ) -> CompanyFundamentals:
        """Return the fundamentals for ``symbol``."""
        if self._fundamental is None:
            raise DataNotFoundError("No fundamental repository configured")
        return self._fundamental.get_fundamentals(symbol=symbol, report_date=report_date)

    # -- news data queries --------------------------------------------------

    def get_articles(
        self,
        symbol: str | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsArticle]:
        """Return news articles, optionally filtered by symbol and date range."""
        if self._news is None:
            raise DataNotFoundError("No news repository configured")
        return self._news.get_articles(
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
        )

    def get_sentiment(self, article_id: str) -> SentimentEvaluation | None:
        """Return the latest sentiment evaluation for an article."""
        if self._news is None:
            raise DataNotFoundError("No news repository configured")
        return self._news.get_sentiment(article_id)

    def get_sentiment_history(
        self, article_id: str, *, since: datetime | None = None
    ) -> list[SentimentEvaluation]:
        """Return the sentiment history for an article."""
        if self._news is None:
            raise DataNotFoundError("No news repository configured")
        return self._news.get_sentiment_history(article_id, since=since)

    # -- portfolio data queries ---------------------------------------------

    def store_position(self, position: PortfolioPosition) -> PortfolioPosition:
        """Store or update the current position (AIOS-402 section 8)."""
        if self._portfolio is None:
            raise DataNotFoundError("No portfolio repository configured")
        return self._portfolio.upsert_position(position)

    def get_position(self, symbol: str, exchange: str) -> PortfolioPosition:
        """Return the current position for ``symbol``/``exchange``."""
        if self._portfolio is None:
            raise DataNotFoundError("No portfolio repository configured")
        return self._portfolio.get_position(symbol=symbol, exchange=exchange)

    def list_positions(self, *, status: PositionStatus | None = None) -> list[PortfolioPosition]:
        """Return portfolio positions, optionally filtered by status."""
        if self._portfolio is None:
            raise DataNotFoundError("No portfolio repository configured")
        return self._portfolio.list_positions(status=status)

    def get_positions_by_sector(self, sector: str) -> list[PortfolioPosition]:
        """Return the open positions classified under ``sector``."""
        if self._portfolio is None:
            raise DataNotFoundError("No portfolio repository configured")
        return self._portfolio.get_positions_by_sector(sector)

    # -- decision data queries ----------------------------------------------

    def store_decisions(self, decisions: list[InvestmentDecision]) -> int:
        """Append investment decisions, returning the number stored (AIOS-402)."""
        if self._decision is None:
            raise DataNotFoundError("No decision repository configured")
        return self._decision.add_decisions(decisions)

    def get_decisions(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[InvestmentDecision]:
        """Return the decision history for ``symbol``."""
        if self._decision is None:
            raise DataNotFoundError("No decision repository configured")
        return self._decision.get_decisions(symbol=symbol, start=start, end=end, limit=limit)

    def get_latest_decision(self, symbol: str) -> InvestmentDecision:
        """Return the most recent decision for ``symbol``."""
        if self._decision is None:
            raise DataNotFoundError("No decision repository configured")
        return self._decision.get_latest_decision(symbol)

    # -- paper trading data queries ------------------------------------------

    def store_paper_order(self, order: PaperOrder) -> PaperOrder:
        """Append a submitted paper order (AIOS-407 section 4.3)."""
        if self._paper_order is None:
            raise DataNotFoundError("No paper order repository configured")
        return self._paper_order.add_order(order)

    def get_paper_order(self, order_id: str) -> PaperOrder:
        """Return the paper order identified by ``order_id``."""
        if self._paper_order is None:
            raise DataNotFoundError("No paper order repository configured")
        return self._paper_order.get_order(order_id)

    def list_paper_orders(self, *, status: OrderStatus | None = None) -> list[PaperOrder]:
        """Return paper orders, optionally filtered by status."""
        if self._paper_order is None:
            raise DataNotFoundError("No paper order repository configured")
        return self._paper_order.list_orders(status=status)

    def update_paper_order(self, order: PaperOrder) -> PaperOrder:
        """Apply a lifecycle update to a stored paper order (AIOS-1103)."""
        if self._paper_order is None:
            raise DataNotFoundError("No paper order repository configured")
        return self._paper_order.update_order(order)

    def store_paper_fill(self, fill: PaperFill) -> PaperFill:
        """Record a paper fill (immutable execution history, AIOS-101)."""
        if self._paper_fill is None:
            raise DataNotFoundError("No paper fill repository configured")
        return self._paper_fill.add_fill(fill)

    def list_paper_fills(self, *, order_id: str | None = None) -> list[PaperFill]:
        """Return recorded paper fills, optionally filtered by ``order_id``."""
        if self._paper_fill is None:
            raise DataNotFoundError("No paper fill repository configured")
        return self._paper_fill.list_fills(order_id=order_id)

    def store_paper_position(self, position: BrokerPosition) -> BrokerPosition:
        """Store or update the broker-side paper position (AIOS-603 section 11)."""
        if self._paper_position is None:
            raise DataNotFoundError("No paper position repository configured")
        return self._paper_position.upsert_position(position)

    def list_paper_positions(self) -> list[BrokerPosition]:
        """Return the current broker-side paper positions."""
        if self._paper_position is None:
            raise DataNotFoundError("No paper position repository configured")
        return self._paper_position.list_positions()

    def store_broker_account(self, account: BrokerAccount) -> BrokerAccount:
        """Store or update the paper broker account (AIOS-407 "Check Account")."""
        if self._broker_account is None:
            raise DataNotFoundError("No broker account repository configured")
        return self._broker_account.upsert_account(account)

    def get_broker_account(self, broker_id: str) -> BrokerAccount:
        """Return the paper broker account for ``broker_id``."""
        if self._broker_account is None:
            raise DataNotFoundError("No broker account repository configured")
        return self._broker_account.get_account(broker_id)
