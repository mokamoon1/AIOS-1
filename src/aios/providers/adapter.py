"""Data Provider Adapter Interface (AIOS-505, AIOS-607).

The Adapter layer translates provider-specific responses into AIOS standard
models and orchestrates the ingestion flow through the Data Pipeline and
repositories. This decouples provider implementations from the ingestion
orchestration logic.
"""

from __future__ import annotations

from collections.abc import Sequence
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


@runtime_checkable
class DataProviderAdapter(Protocol):
    """Adapter protocol for data providers.

    Adapters bridge the gap between provider interfaces and the ingestion
    system. They handle data transformation, batching, and coordinate with
    the IngestionService for validation and storage.
    """

    @property
    def name(self) -> str:
        """Return the stable adapter name used for registration."""
        ...

    @property
    def provider_name(self) -> str:
        """Return the underlying provider name."""
        ...

    # -- Market Data --
    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        """Fetch standardized candles from the provider."""
        ...

    async def fetch_security(self, symbol: str, exchange: str) -> Security:
        """Fetch standardized security entity from the provider."""
        ...

    # -- Shariah Data --
    async def fetch_compliance(self, symbol: str) -> ShariahCompliance:
        """Fetch standardized compliance record from the provider."""
        ...

    async def fetch_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]:
        """Fetch compliance history for the symbol."""
        ...

    # -- Fundamental Data --
    async def fetch_fundamentals(self, symbol: str) -> CompanyFundamentals:
        """Fetch standardized company fundamentals from the provider."""
        ...


@runtime_checkable
class MarketDataAdapter(DataProviderAdapter, Protocol):
    """Adapter specialized for market data (candles and securities)."""

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]: ...

    async def fetch_security(self, symbol: str, exchange: str) -> Security: ...


@runtime_checkable
class ShariahDataAdapter(DataProviderAdapter, Protocol):
    """Adapter specialized for Shariah compliance data."""

    async def fetch_compliance(self, symbol: str) -> ShariahCompliance: ...

    async def fetch_compliance_history(
        self, symbol: str, *, since: date | None = None
    ) -> list[ShariahCompliance]: ...


@runtime_checkable
class FundamentalDataAdapter(DataProviderAdapter, Protocol):
    """Adapter specialized for fundamental data."""

    async def fetch_fundamentals(self, symbol: str) -> CompanyFundamentals: ...


@runtime_checkable
class NewsDataAdapter(DataProviderAdapter, Protocol):
    """Adapter specialized for news data."""

    async def fetch_news(
        self,
        symbols: list[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsArticle]: ...

    async def fetch_sentiment(self, article: NewsArticle) -> SentimentEvaluation: ...


# -- Ingestion Result Types --

from dataclasses import dataclass, field
from enum import Enum


class IngestionResultType(str, Enum):
    """Result type for an ingestion operation."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class IngestionResult:
    """Result of a single ingestion operation."""

    dataset_id: str
    provider_name: str
    result_type: IngestionResultType
    records_fetched: int = 0
    records_validated: int = 0
    records_stored: int = 0
    error_message: str | None = None
    validation_report: str | None = None


@dataclass
class BatchIngestionResult:
    """Result of a batch ingestion operation across multiple symbols."""

    total_symbols: int
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    quarantined: int = 0
    total_records_fetched: int = 0
    total_records_stored: int = 0
    results: list[IngestionResult] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)

    def add_result(self, result: IngestionResult) -> None:
        """Add a single ingestion result to the batch."""
        self.results.append(result)
        self.total_records_fetched += result.records_fetched
        self.total_records_stored += result.records_stored
        if result.result_type == IngestionResultType.SUCCESS:
            self.successful += 1
        elif result.result_type == IngestionResultType.FAILED:
            self.failed += 1
            if result.error_message:
                self.error_messages.append(result.error_message)
        elif result.result_type == IngestionResultType.SKIPPED:
            self.skipped += 1
        elif result.result_type == IngestionResultType.QUARANTINED:
            self.quarantined += 1

    def summary(self) -> str:
        """Return a human-readable summary."""
        return (
            f"Batch: {self.total_symbols} symbols, "
            f"{self.successful} success, {self.failed} failed, "
            f"{self.skipped} skipped, {self.quarantined} quarantined, "
            f"{self.total_records_fetched} fetched, {self.total_records_stored} stored"
        )