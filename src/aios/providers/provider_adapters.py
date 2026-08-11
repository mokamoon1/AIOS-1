"""Provider Adapter Implementations (AIOS-505, AIOS-607).

Concrete adapters that wrap data providers and translate their interface
to the adapter protocol expected by the IngestionService.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Sequence

from aios.analysis.news import NewsArticle, SentimentEvaluation
from aios.data.models import (
    Candle,
    CompanyFundamentals,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.providers.adapter import (
    DataProviderAdapter,
    FundamentalDataAdapter,
    MarketDataAdapter,
    NewsDataAdapter,
    ShariahDataAdapter,
)
from aios.providers.interfaces import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
    ShariahDataProvider,
)


class MarketDataProviderAdapter:
    """Adapter wrapping a MarketDataProvider to implement MarketDataAdapter protocol."""

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._provider = provider
        self._logger = logger or logging.getLogger("aios.providers.adapter.market")

    @property
    def name(self) -> str:
        return f"{self._provider.name}-adapter"

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        return await self._provider.get_candles(
            symbol, timeframe, start=start, end=end, limit=limit
        )

    async def fetch_security(self, symbol: str, exchange: str) -> Security:
        return await self._provider.get_security(symbol, exchange)

    async def fetch_compliance(self, symbol: str) -> ShariahCompliance:
        raise NotImplementedError("Market adapter does not provide compliance data")

    async def fetch_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]:
        raise NotImplementedError("Market adapter does not provide compliance history")

    async def fetch_fundamentals(self, symbol: str) -> CompanyFundamentals:
        raise NotImplementedError("Market adapter does not provide fundamental data")


class ShariahDataProviderAdapter:
    """Adapter wrapping a ShariahDataProvider to implement ShariahDataAdapter protocol."""

    def __init__(
        self,
        provider: ShariahDataProvider,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._provider = provider
        self._logger = logger or logging.getLogger("aios.providers.adapter.shariah")

    @property
    def name(self) -> str:
        return f"{self._provider.name}-adapter"

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        raise NotImplementedError("Shariah adapter does not provide candle data")

    async def fetch_security(self, symbol: str, exchange: str) -> Security:
        raise NotImplementedError("Shariah adapter does not provide security data")

    async def fetch_compliance(self, symbol: str) -> ShariahCompliance:
        return await self._provider.get_compliance(symbol)

    async def fetch_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]:
        return await self._provider.get_compliance_history(symbol, since=since)

    async def fetch_fundamentals(self, symbol: str) -> CompanyFundamentals:
        raise NotImplementedError("Shariah adapter does not provide fundamental data")


class FundamentalDataProviderAdapter:
    """Adapter wrapping a FundamentalDataProvider to implement FundamentalDataAdapter protocol."""

    def __init__(
        self,
        provider: FundamentalDataProvider,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._provider = provider
        self._logger = logger or logging.getLogger("aios.providers.adapter.fundamental")

    @property
    def name(self) -> str:
        return f"{self._provider.name}-adapter"

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        raise NotImplementedError("Fundamental adapter does not provide candle data")

    async def fetch_security(self, symbol: str, exchange: str) -> Security:
        raise NotImplementedError("Fundamental adapter does not provide security data")

    async def fetch_compliance(self, symbol: str) -> ShariahCompliance:
        raise NotImplementedError("Fundamental adapter does not provide compliance data")

    async def fetch_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]:
        raise NotImplementedError("Fundamental adapter does not provide compliance history")

    async def fetch_fundamentals(self, symbol: str) -> CompanyFundamentals:
        return await self._provider.get_fundamentals(symbol)


class NewsDataProviderAdapter:
    """Adapter wrapping a NewsDataProvider to implement NewsDataAdapter protocol."""

    def __init__(
        self,
        provider: NewsDataProvider,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._provider = provider
        self._logger = logger or logging.getLogger("aios.providers.adapter.news")

    @property
    def name(self) -> str:
        return f"{self._provider.name}-adapter"

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        raise NotImplementedError("News adapter does not provide candle data")

    async def fetch_security(self, symbol: str, exchange: str) -> Security:
        raise NotImplementedError("News adapter does not provide security data")

    async def fetch_compliance(self, symbol: str) -> ShariahCompliance:
        raise NotImplementedError("News adapter does not provide compliance data")

    async def fetch_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]:
        raise NotImplementedError("News adapter does not provide compliance history")

    async def fetch_fundamentals(self, symbol: str) -> CompanyFundamentals:
        raise NotImplementedError("News adapter does not provide fundamental data")

    async def fetch_news(
        self,
        symbols: list[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsArticle]:
        return await self._provider.get_news(
            symbols, start=start, end=end, limit=limit
        )

    async def fetch_sentiment(self, article: NewsArticle) -> SentimentEvaluation:
        return await self._provider.get_sentiment(article)


# Protocol conformance verification
assert isinstance(
    MarketDataProviderAdapter.__new__(MarketDataProviderAdapter), MarketDataAdapter
)
assert isinstance(
    ShariahDataProviderAdapter.__new__(ShariahDataProviderAdapter), ShariahDataAdapter
)
assert isinstance(
    FundamentalDataProviderAdapter.__new__(FundamentalDataProviderAdapter),
    FundamentalDataAdapter,
)
assert isinstance(
    NewsDataProviderAdapter.__new__(NewsDataProviderAdapter), NewsDataAdapter
)
assert isinstance(
    MarketDataProviderAdapter.__new__(MarketDataProviderAdapter), DataProviderAdapter
)
assert isinstance(
    ShariahDataProviderAdapter.__new__(ShariahDataProviderAdapter), DataProviderAdapter
)
assert isinstance(
    FundamentalDataProviderAdapter.__new__(FundamentalDataProviderAdapter),
    DataProviderAdapter,
)
assert isinstance(
    NewsDataProviderAdapter.__new__(NewsDataProviderAdapter), DataProviderAdapter
)