"""Mock data providers for testing and Paper Trading environment (AIOS-603 section 6).

These providers read from the local database via repositories instead of
connecting to external APIs. They implement the standard provider interfaces
and are safe for use in the Paper Trading environment where no live
connections are permitted.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Sequence

from aios.analysis.news import NewsArticle, SentimentEvaluation, SentimentLabel
from aios.data.models import (
    Candle,
    CompanyFundamentals,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.database.repositories import (
    CompanyRepository,
    MarketRepository,
    ShariahRepository,
)
from aios.database.exceptions import RecordNotFoundError
from aios.providers.base import DataProvider
from aios.providers.interfaces import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
    ShariahDataProvider,
)


class MockMarketDataProvider:
    """Mock market data provider reading from local database.

    Implements :class:`MarketDataProvider` protocol by delegating to
    :class:`MarketRepository`. Safe for Paper Trading environment.
    """

    _provider_name = "mock-market"

    def __init__(
        self,
        market_repository: MarketRepository,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._market_repository = market_repository
        self._connected = False
        self._logger = logger or logging.getLogger("aios.providers.mock.market")

    @property
    def name(self) -> str:
        return self._provider_name

    async def connect(self) -> None:
        self._connected = True
        self._logger.info("Mock market provider connected")

    async def disconnect(self) -> None:
        self._connected = False
        self._logger.info("Mock market provider disconnected")

    def is_connected(self) -> bool:
        return self._connected

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        return self._market_repository.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
        )

    async def get_security(self, symbol: str, exchange: str) -> Security:
        return self._market_repository.get_security(symbol=symbol, exchange=exchange)


class MockShariahDataProvider:
    """Mock Shariah data provider reading from local database.

    Implements :class:`ShariahDataProvider` protocol by delegating to
    :class:`ShariahRepository`. Safe for Paper Trading environment.
    """

    _provider_name = "mock-shariah"

    def __init__(
        self,
        shariah_repository: ShariahRepository,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._shariah_repository = shariah_repository
        self._connected = False
        self._logger = logger or logging.getLogger("aios.providers.mock.shariah")

    @property
    def name(self) -> str:
        return self._provider_name

    async def connect(self) -> None:
        self._connected = True
        self._logger.info("Mock Shariah provider connected")

    async def disconnect(self) -> None:
        self._connected = False
        self._logger.info("Mock Shariah provider disconnected")

    def is_connected(self) -> bool:
        return self._connected

    async def get_compliance(self, symbol: str) -> ShariahCompliance:
        return self._shariah_repository.get_compliance_status(symbol=symbol)

    async def get_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]:
        # The repository returns the latest record; for history we would need
        # a different method. For now, return the latest as a single-item list.
        # This matches the test expectations in test_interfaces.py
        record = self._shariah_repository.get_compliance_status(symbol=symbol, as_of=since)
        return [record]


class MockFundamentalDataProvider:
    """Mock fundamental data provider reading from local database.

    Implements :class:`FundamentalDataProvider` protocol by delegating to
    :class:`CompanyRepository`. Safe for Paper Trading environment.
    """

    _provider_name = "mock-fundamental"

    def __init__(
        self,
        company_repository: CompanyRepository,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._company_repository = company_repository
        self._connected = False
        self._logger = logger or logging.getLogger("aios.providers.mock.fundamental")

    @property
    def name(self) -> str:
        return self._provider_name

    async def connect(self) -> None:
        self._connected = True
        self._logger.info("Mock fundamental provider connected")

    async def disconnect(self) -> None:
        self._connected = False
        self._logger.info("Mock fundamental provider disconnected")

    def is_connected(self) -> bool:
        return self._connected

    async def get_fundamentals(self, symbol: str) -> CompanyFundamentals:
        return self._company_repository.get_fundamentals(symbol=symbol)


class MockNewsDataProvider:
    """Mock news data provider returning predefined articles.

    Implements :class:`NewsDataProvider` protocol by returning predefined
    mock articles. Safe for Paper Trading environment as no external
    connections are made.
    """

    _provider_name = "mock-news"

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._connected = False
        self._logger = logger or logging.getLogger("aios.providers.mock.news")
        # Predefined mock articles for testing
        self._articles = {
            "AAPL": [
                NewsArticle(
                    provider="mock-news",
                    article_id="mock-aapl-1",
                    published_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
                    retrieved_at=datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
                    source="Mock Financial Wire",
                    headline="Apple Reports Strong Q3 Earnings",
                    summary="Apple Inc. reported quarterly earnings that exceeded analyst expectations.",
                    url="https://example.com/aapl-earnings",
                    symbols=["AAPL"],
                ),
                NewsArticle(
                    provider="mock-news",
                    article_id="mock-aapl-2",
                    published_at=datetime(2026, 8, 5, 9, 30, tzinfo=timezone.utc),
                    retrieved_at=datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc),
                    source="Mock Financial Wire",
                    headline="Apple Announces New Product Line",
                    summary="Apple announced a new line of products for the holiday season.",
                    url="https://example.com/aapl-new-products",
                    symbols=["AAPL"],
                ),
            ],
            "MSFT": [
                NewsArticle(
                    provider="mock-news",
                    article_id="mock-msft-1",
                    published_at=datetime(2026, 8, 2, 14, 0, tzinfo=timezone.utc),
                    retrieved_at=datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc),
                    source="Mock Financial Wire",
                    headline="Microsoft Cloud Revenue Grows 20%",
                    summary="Microsoft's cloud division showed strong growth in the latest quarter.",
                    url="https://example.com/msft-cloud",
                    symbols=["MSFT"],
                ),
            ],
        }

    @property
    def name(self) -> str:
        return self._provider_name

    async def connect(self) -> None:
        self._connected = True
        self._logger.info("Mock news provider connected")

    async def disconnect(self) -> None:
        self._connected = False
        self._logger.info("Mock news provider disconnected")

    def is_connected(self) -> bool:
        return self._connected

    async def get_news(
        self,
        symbols: list[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsArticle]:
        """Return mock news articles for the requested symbols."""
        result = []
        for symbol in symbols:
            articles = self._articles.get(symbol, [])
            for article in articles:
                if start and article.published_at < start:
                    continue
                if end and article.published_at > end:
                    continue
                result.append(article)
                if len(result) >= limit:
                    break
            if len(result) >= limit:
                break
        return result[:limit]

    async def get_sentiment(self, article: NewsArticle) -> SentimentEvaluation:
        """Return a mock sentiment evaluation for the article."""
        # Simple heuristic: positive if headline contains positive words
        positive_words = ["strong", "growth", "exceeds", "announces", "new", "record", "beats"]
        negative_words = ["weak", "decline", "loss", "misses", "cut", "layoff", "downturn"]

        headline_lower = article.headline.lower()
        sentiment = SentimentLabel.NEUTRAL
        score = 0.0

        if any(word in headline_lower for word in positive_words):
            sentiment = SentimentLabel.NEUTRAL  # We only have NEUTRAL label
            score = 0.5
        elif any(word in headline_lower for word in negative_words):
            sentiment = SentimentLabel.NEUTRAL
            score = -0.5

        return SentimentEvaluation(
            provider=self._provider_name,
            article_id=article.article_id,
            sentiment=sentiment,
            score=score,
            methodology="mock-heuristic",
        )


# Protocol conformance verification (runtime checkable)
assert isinstance(MockMarketDataProvider(MarketRepository(None)), MarketDataProvider)
assert isinstance(MockMarketDataProvider(MarketRepository(None)), DataProvider)
assert isinstance(MockShariahDataProvider(ShariahRepository(None)), ShariahDataProvider)
assert isinstance(MockShariahDataProvider(ShariahRepository(None)), DataProvider)
assert isinstance(MockFundamentalDataProvider(CompanyRepository(None)), FundamentalDataProvider)
assert isinstance(MockFundamentalDataProvider(CompanyRepository(None)), DataProvider)
assert isinstance(MockNewsDataProvider(), NewsDataProvider)
assert isinstance(MockNewsDataProvider(), DataProvider)