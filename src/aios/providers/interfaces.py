"""Data provider interfaces (AIOS-603 section 6, AIOS-607).

Every provider translates external responses into AIOS standard models
(AIOS-603 section 6); provider-specific structures never reach engines.
The response lifecycle follows AIOS-607 section 7: prepare, authenticate,
send, receive, validate, normalize, return a standardized result. API
clients contain no business logic (AIOS-607 section 5).

These protocols extend :class:`aios.providers.base.DataProvider`. No
concrete external provider is wired in this phase; providers implement
these interfaces and register with the ProviderManager.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from aios.analysis.news import NewsArticle, SentimentEvaluation
from aios.data.models import (
    Candle,
    CompanyFundamentals,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.providers.base import DataProvider


@runtime_checkable
class MarketDataProvider(DataProvider, Protocol):
    """Market data provider returning AIOS standard market models."""

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        """Return standardized candles (AIOS-503 section 5).

        The provider validates the external response before returning it;
        invalid responses are rejected (AIOS-607 section 11).
        """
        ...

    async def get_security(self, symbol: str, exchange: str) -> Security:
        """Return the standardized security entity (AIOS-503 section 4)."""
        ...


@runtime_checkable
class ShariahDataProvider(DataProvider, Protocol):
    """Shariah data provider returning AIOS standard compliance records."""

    async def get_compliance(self, symbol: str) -> ShariahCompliance:
        """Return the standardized compliance record (AIOS-504)."""
        ...

    async def get_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]:
        """Return the compliance history for ``symbol`` (AIOS-504 section 9)."""
        ...


@runtime_checkable
class FundamentalDataProvider(DataProvider, Protocol):
    """Financial statement provider returning AIOS standard fundamentals."""

    async def get_fundamentals(self, symbol: str) -> CompanyFundamentals:
        """Return the standardized company fundamentals (AIOS-502 section 6)."""
        ...


@runtime_checkable
class NewsDataProvider(DataProvider, Protocol):
    """News data provider returning AIOS standard news articles.

    News data providers collect and standardize news articles from external
    sources. The provider validates the external response before returning it;
    invalid responses are rejected (AIOS-607 section 11).
    """

    async def get_news(
        self,
        symbols: list[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsArticle]:
        """Return standardized news articles for the requested symbols.

        The provider validates the external response before returning it.
        """
        ...

    async def get_sentiment(self, article: NewsArticle) -> SentimentEvaluation:
        """Return sentiment evaluation for a news article.

        The provider validates the external response before returning it.
        """
        ...
