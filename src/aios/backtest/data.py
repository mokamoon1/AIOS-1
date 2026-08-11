"""Backtest Data Service - Point-in-time historical data access (Phase 9.5).

Provides a DataService-compatible facade that enforces point-in-time data access
with a mandatory current_time ceiling to prevent look-ahead bias.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any, Protocol

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
from aios.data.services import DataService


class BacktestDataService:
    """Data Service wrapper that enforces point-in-time historical access.

    All queries are bounded by the current backtest timestamp to prevent
    look-ahead bias. The current_time is set by the BacktestOrchestrator
    and acts as a ceiling for all temporal queries.

    This wrapper delegates to the underlying DataService repositories but
    enforces temporal ceilings on all temporal queries.
    """

    def __init__(
        self,
        base_service: DataService,
        current_time: datetime,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        if current_time.tzinfo is None:
            raise ValueError("current_time must be timezone-aware (UTC)")
        self._base = base_service
        self._current_time = current_time
        self._logger = logger or logging.getLogger("aios.backtest.data")

    @property
    def current_time(self) -> datetime:
        """Return the current backtest timestamp (ceiling for all queries)."""
        return self._current_time

    def set_current_time(self, current_time: datetime) -> None:
        """Advance the backtest clock. Must be called by BacktestOrchestrator."""
        if current_time.tzinfo is None:
            raise ValueError("current_time must be timezone-aware (UTC)")
        if current_time < self._current_time:
            raise ValueError("current_time cannot go backwards")
        self._current_time = current_time
        self._logger.debug("Backtest clock advanced to %s", current_time.isoformat())

    # -- market data queries -----------------------------------------------

    def get_candles(
        self,
        symbol: str,
        timeframe: Any,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[Any]:
        """Return candles with timestamp <= current_time.

        The end parameter is clamped to current_time to prevent look-ahead.
        """
        if self._base._market is None:
            raise DataNotFoundError("No market repository configured")

        # Clamp end to current_time - this is the critical look-ahead prevention
        effective_end = end
        if effective_end is None or effective_end > self._current_time:
            effective_end = self._current_time

        return self._base._market.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=effective_end,
            limit=limit,
        )

    def get_security(self, symbol: str, exchange: str) -> Any:
        """Return the security entity (no temporal restriction needed)."""
        return self._base.get_security(symbol, exchange)

    # -- Shariah data queries ----------------------------------------------

    def get_compliance_status(self, symbol: str, *, as_of: date | None = None) -> Any:
        """Return Shariah compliance status as of the given date.

        The as_of date is clamped to current_time to prevent look-ahead.
        The Shariah repository filters by effective_date/expiration_date.
        """
        if self._base._shariah is None:
            raise DataNotFoundError("No Shariah repository configured")

        # Clamp as_of to current_time
        effective_as_of = as_of
        if effective_as_of is None or effective_as_of > self._current_time.date():
            effective_as_of = self._current_time.date()

        return self._base._shariah.get_compliance_status(symbol=symbol, as_of=effective_as_of)

    # -- fundamental data queries ------------------------------------------

    def get_fundamentals(
        self, symbol: str, *, report_date: date | None = None
    ) -> Any:
        """Return fundamentals for symbol as of report_date.

        The report_date is clamped to current_time to prevent look-ahead.
        """
        if self._base._fundamental is None:
            raise DataNotFoundError("No fundamental repository configured")

        # Clamp report_date to current_time
        effective_report_date = report_date
        if effective_report_date is None or effective_report_date > self._current_time.date():
            effective_report_date = self._current_time.date()

        return self._base._fundamental.get_fundamentals(symbol=symbol, report_date=effective_report_date)

    # -- news data queries --------------------------------------------------

    def get_articles(
        self,
        symbol: str | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """Return news articles with published_at <= current_time."""
        if self._base._news is None:
            raise DataNotFoundError("No news repository configured")

        # Clamp end to current_time
        effective_end = end
        if effective_end is None or effective_end > self._current_time:
            effective_end = self._current_time

        return self._base._news.get_articles(
            symbol=symbol,
            start=start,
            end=effective_end,
            limit=limit,
        )

    def get_sentiment(self, article_id: str) -> Any | None:
        """Return latest sentiment evaluation for an article (temporal restriction to current_time)."""
        sentiment = self._base.get_sentiment(article_id)
        if sentiment is not None and sentiment.evaluated_at > self._current_time:
            return None
        return sentiment

    def get_sentiment_history(
        self, article_id: str, *, since: datetime | None = None
    ) -> list[Any]:
        """Return sentiment history for an article, filtered by evaluated_at <= current_time."""
        if self._base._news is None:
            raise DataNotFoundError("No news repository configured")

        history = self._base._news.get_sentiment_history(article_id, since=since)
        # Filter by evaluated_at <= current_time
        return [eval for eval in history if eval.evaluated_at <= self._current_time]

    # -- portfolio data queries ---------------------------------------------

    def store_position(self, position: Any) -> Any:
        return self._base.store_position(position)

    def get_position(self, symbol: str, exchange: str) -> Any:
        return self._base.get_position(symbol, exchange)

    def list_positions(self, *, status: Any | None = None) -> list[Any]:
        return self._base.list_positions(status=status)

    def get_positions_by_sector(self, sector: str) -> list[Any]:
        return self._base.get_positions_by_sector(sector)

    # -- decision data queries ----------------------------------------------

    def store_decisions(self, decisions: list[Any]) -> int:
        for decision in decisions:
            if decision.timestamp > self._current_time:
                raise ValueError(f"Decision timestamp {decision.timestamp} is in the future relative to backtest time {self._current_time}")
        return self._base.store_decisions(decisions)

    def get_decisions(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Any]:
        if self._base._decision is None:
            raise DataNotFoundError("No decision repository configured")

        # Clamp end to current_time
        effective_end = end
        if effective_end is None or effective_end > self._current_time:
            effective_end = self._current_time

        return self._base._decision.get_decisions(
            symbol=symbol, start=start, end=effective_end, limit=limit
        )

    def get_latest_decision(self, symbol: str) -> Any:
        decision = self._base.get_latest_decision(symbol)
        if decision is not None and decision.timestamp > self._current_time:
            return None
        return decision

    # -- paper trading data queries -----------------------------------------

    def store_paper_order(self, order: Any) -> Any:
        if hasattr(order, 'submitted_at') and order.submitted_at > self._current_time:
            raise ValueError(f"Order submitted_at {order.submitted_at} is in the future relative to backtest time {self._current_time}")
        return self._base.store_paper_order(order)

    def get_paper_order(self, order_id: str) -> Any:
        return self._base.get_paper_order(order_id)

    def list_paper_orders(self, *, status: Any | None = None) -> list[Any]:
        return self._base.list_paper_orders(status=status)

    def update_paper_order(self, order: Any) -> Any:
        if hasattr(order, 'updated_at') and order.updated_at > self._current_time:
            raise ValueError(f"Order updated_at {order.updated_at} is in the future relative to backtest time {self._current_time}")
        return self._base.update_paper_order(order)

    def store_paper_fill(self, fill: Any) -> Any:
        if hasattr(fill, 'filled_at') and fill.filled_at > self._current_time:
            raise ValueError(f"Fill filled_at {fill.filled_at} is in the future relative to backtest time {self._current_time}")
        return self._base.store_paper_fill(fill)

    def list_paper_fills(self, *, order_id: str | None = None) -> list[Any]:
        return self._base.list_paper_fills(order_id=order_id)

    def store_paper_position(self, position: Any) -> Any:
        if hasattr(position, 'updated_at') and position.updated_at > self._current_time:
            raise ValueError(f"Position updated_at {position.updated_at} is in the future relative to backtest time {self._current_time}")
        return self._base.store_paper_position(position)

    def list_paper_positions(self) -> list[Any]:
        return self._base.list_paper_positions()

    def store_broker_account(self, account: Any) -> Any:
        if hasattr(account, 'updated_at') and account.updated_at > self._current_time:
            raise ValueError(f"Account updated_at {account.updated_at} is in the future relative to backtest time {self._current_time}")
        return self._base.store_broker_account(account)

    def get_broker_account(self, broker_id: str) -> Any:
        return self._base.get_broker_account(broker_id)

    # -- ingestion delegation ------------------------------------------------

    async def ingest_candles(
        self,
        *,
        dataset_id: str,
        provider_name: str,
        fetch: Any,
        store: Any,
        quarantine_on_warning: bool = False,
    ) -> Any:
        """Delegate to pipeline (not used in backtest replay)."""
        return await self._base.ingest_candles(
            dataset_id=dataset_id,
            provider_name=provider_name,
            fetch=fetch,
            store=store,
            quarantine_on_warning=quarantine_on_warning,
        )