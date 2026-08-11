"""Data Ingestion Service (AIOS-505, AIOS-607).

Orchestrates data ingestion from providers through adapters, validation,
and storage. Supports both single-symbol and batch/historical ingestion.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from aios.data.exceptions import DataPipelineError, DataValidationError
from aios.data.models import (
    Candle,
    CompanyFundamentals,
    Security,
    ShariahCompliance,
    Timeframe,
)
from aios.analysis.news import NewsArticle
from aios.data.pipeline import DataPipeline, PipelineRun
from aios.data.validation import DataValidator, ValidationReport, ValidationResult

# Use string annotations for adapter types to avoid circular imports
# The actual imports happen inside methods at runtime


@dataclass(frozen=True)
class IngestionConfig:
    """Configuration for ingestion operations."""

    batch_size: int = 100
    rate_limit_ms: int = 0
    max_concurrent: int = 1
    quarantine_on_warning: bool = False
    freshness_max_age_days: int | None = None
    default_exchange: str = "NASDAQ"


class IngestionService:
    """Orchestrates data ingestion from adapters through validation to storage.

    The service coordinates:
    1. Fetching data from provider adapters
    2. Validating data through DataValidator
    3. Storing validated data via repositories (or DataPipeline for candles)
    4. Batch/historical ingestion with progress tracking and idempotency
    """

    def __init__(
        self,
        *,
        pipeline: DataPipeline,
        validator: DataValidator,
        market_adapter: "DataProviderAdapter" | None = None,
        shariah_adapter: "DataProviderAdapter" | None = None,
        fundamental_adapter: "DataProviderAdapter" | None = None,
        news_adapter: "DataProviderAdapter" | None = None,
        market_repository: Any | None = None,
        shariah_repository: Any | None = None,
        fundamental_repository: Any | None = None,
        news_repository: Any | None = None,
        config: IngestionConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._validator = validator
        self._market_adapter = market_adapter
        self._shariah_adapter = shariah_adapter
        self._fundamental_adapter = fundamental_adapter
        self._news_adapter = news_adapter
        self._market_repo = market_repository
        self._shariah_repo = shariah_repository
        self._fundamental_repo = fundamental_repository
        self._news_repo = news_repository
        self._config = config or IngestionConfig()
        self._logger = logger or logging.getLogger("aios.data.ingestion")

    # -- Single Symbol Ingestion --

    async def ingest_market_data(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
        dataset_id: str | None = None,
    ) -> "IngestionResult":
        """Ingest market data (candles + security) for a single symbol."""
        from aios.providers.adapter import IngestionResult, IngestionResultType

        provider_name = getattr(self._market_adapter, "provider_name", None) or getattr(self._market_adapter, "name", "unknown")
        did = dataset_id or f"market-{symbol}-{timeframe.value}-{int(time.time())}"

        if not self._market_adapter or not self._market_repo:
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.SKIPPED,
                error_message="Market adapter or repository not configured",
            )

        try:
            # Fetch candles and security
            candles = await self._market_adapter.fetch_candles(
                symbol, timeframe, start=start, end=end, limit=limit
            )
            security = await self._market_adapter.fetch_security(symbol, self._config.default_exchange)

            if not candles:
                return IngestionResult(
                    dataset_id=did,
                    provider_name=provider_name,
                    result_type=IngestionResultType.SKIPPED,
                    records_fetched=0,
                    error_message="No candles returned",
                )

            # Validate through pipeline
            run = await self._pipeline.ingest_candles(
                dataset_id=did,
                provider_name=provider_name,
                fetch=lambda: candles,
                store=lambda c: self._market_repo.add_candles(c, provider_name),
                quarantine_on_warning=self._config.quarantine_on_warning,
            )

            # Store security (idempotent)
            self._market_repo.add_security(security)

            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.SUCCESS
                if run.validation_result != ValidationResult.QUARANTINED
                else IngestionResultType.QUARANTINED,
                records_fetched=run.records_ingested,
                records_validated=run.records_normalized,
                records_stored=run.records_stored,
                validation_report=run.validation.summary() if run.validation else None,
            )

        except DataValidationError as exc:
            self._logger.warning("Validation failed for %s: %s", did, exc)
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.QUARANTINED,
                error_message=str(exc),
            )
        except (DataPipelineError, Exception) as exc:  # noqa: BLE001
            self._logger.exception("Ingestion failed for %s", did)
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.FAILED,
                error_message=str(exc),
            )

    async def ingest_shariah_data(
        self,
        symbol: str,
        *,
        dataset_id: str | None = None,
    ) -> "IngestionResult":
        """Ingest Shariah compliance data for a single symbol."""
        from aios.providers.adapter import IngestionResult, IngestionResultType

        provider_name = getattr(self._shariah_adapter, "provider_name", None) or getattr(self._shariah_adapter, "name", "unknown")
        did = dataset_id or f"shariah-{symbol}-{int(time.time())}"

        if not self._shariah_adapter or not self._shariah_repo:
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.SKIPPED,
                error_message="Shariah adapter or repository not configured",
            )

        try:
            record = await self._shariah_adapter.fetch_compliance(symbol)
            if record is None:
                return IngestionResult(
                    dataset_id=did,
                    provider_name=provider_name,
                    result_type=IngestionResultType.SKIPPED,
                    records_fetched=0,
                    error_message="No compliance record returned",
                )

            # Validate
            report = self._validator.validate_compliance(did, [record])
            if report.result == ValidationResult.INVALID:
                raise DataValidationError(f"Validation failed: {report.summary()}")

            if report.result == ValidationResult.QUARANTINED:
                return IngestionResult(
                    dataset_id=did,
                    provider_name=provider_name,
                    result_type=IngestionResultType.QUARANTINED,
                    records_fetched=1,
                    validation_report=report.summary(),
                )

            # Store
            stored = self._shariah_repo.add_records([record])

            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.SUCCESS,
                records_fetched=1,
                records_validated=1,
                records_stored=stored,
                validation_report=report.summary(),
            )

        except DataValidationError as exc:
            self._logger.warning("Validation failed for %s: %s", did, exc)
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.QUARANTINED,
                error_message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Ingestion failed for %s", did)
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.FAILED,
                error_message=str(exc),
            )

    async def ingest_fundamentals(
        self,
        symbol: str,
        *,
        dataset_id: str | None = None,
    ) -> "IngestionResult":
        """Ingest fundamental data for a single symbol."""
        from aios.providers.adapter import IngestionResult, IngestionResultType

        provider_name = getattr(self._fundamental_adapter, "provider_name", None) or getattr(self._fundamental_adapter, "name", "unknown")
        did = dataset_id or f"fundamental-{symbol}-{int(time.time())}"

        if not self._fundamental_adapter or not self._fundamental_repo:
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.SKIPPED,
                error_message="Fundamental adapter or repository not configured",
            )

        try:
            record = await self._fundamental_adapter.fetch_fundamentals(symbol)
            if record is None:
                return IngestionResult(
                    dataset_id=did,
                    provider_name=provider_name,
                    result_type=IngestionResultType.SKIPPED,
                    records_fetched=0,
                    error_message="No fundamentals record returned",
                )

            # Validate
            report = self._validator.validate_fundamentals(did, [record])
            if report.result == ValidationResult.INVALID:
                raise DataValidationError(f"Validation failed: {report.summary()}")

            # Store
            stored = self._fundamental_repo.add_fundamentals([record])

            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.SUCCESS,
                records_fetched=1,
                records_validated=1,
                records_stored=stored,
                validation_report=report.summary(),
            )

        except DataValidationError as exc:
            self._logger.warning("Validation failed for %s: %s", did, exc)
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.QUARANTINED,
                error_message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Ingestion failed for %s", did)
            return IngestionResult(
                dataset_id=did,
                provider_name=provider_name,
                result_type=IngestionResultType.FAILED,
                error_message=str(exc),
            )

    async def ingest_news(
        self,
        symbols: list[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        dataset_id: str | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> "BatchIngestionResult":
        """Ingest news articles for multiple symbols.

        Args:
            symbols: List of symbols to ingest news for
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            limit: Maximum number of articles per symbol
            dataset_id: Optional dataset identifier
            progress_callback: Optional callback(symbol_index, total, current_symbol)

        Returns:
            BatchIngestionResult with per-symbol ingestion results
        """
        from aios.providers.adapter import BatchIngestionResult

        bs = self._config.batch_size
        rate_limit = self._config.rate_limit_ms / 1000.0 if self._config.rate_limit_ms else 0
        max_concurrent = self._config.max_concurrent

        results = BatchIngestionResult(total_symbols=len(symbols))

        # Process in batches to control memory and rate
        for i in range(0, len(symbols), bs):
            batch = symbols[i : i + bs]
            batch_results = await self._ingest_news_batch(
                batch,
                start,
                end,
                limit,
                rate_limit=rate_limit,
                max_concurrent=max_concurrent,
                progress_callback=progress_callback,
            )
            for r in batch_results.results:
                results.add_result(r)

            if progress_callback:
                progress_callback(min(i + bs, len(symbols)), len(symbols), batch[-1])

        return results

    async def _ingest_news_batch(
        self,
        symbols: list[str],
        start: datetime | None,
        end: datetime | None,
        limit: int,
        *,
        rate_limit: float = 0,
        max_concurrent: int = 1,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> "BatchIngestionResult":
        """Internal batch news ingestion with concurrency and rate limiting."""
        from aios.providers.adapter import BatchIngestionResult

        semaphore = asyncio.Semaphore(max_concurrent)
        results = BatchIngestionResult(total_symbols=len(symbols))

        async def ingest_one(symbol: str) -> "IngestionResult":
            async with semaphore:
                if rate_limit > 0:
                    await asyncio.sleep(rate_limit)
                return await self._ingest_single_symbol_news(symbol, start, end, limit)

        tasks = [ingest_one(s) for s in symbols]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.add_result(result)

        return results

    async def _ingest_single_symbol_news(
        self,
        symbol: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> "IngestionResult":
        """Ingest news for a single symbol."""
        from aios.providers.adapter import IngestionResult, IngestionResultType

        if not self._news_adapter or not self._news_repo:
            return IngestionResult(
                dataset_id=f"news-{symbol}-{int(time.time())}",
                provider_name="unknown",
                result_type=IngestionResultType.SKIPPED,
                error_message="News adapter or repository not configured",
            )

        try:
            articles = await self._news_adapter.fetch_news([symbol], start=start, end=end, limit=limit)
            if not articles:
                return IngestionResult(
                    dataset_id=f"news-{symbol}-{int(time.time())}",
                    provider_name="unknown",
                    result_type=IngestionResultType.SKIPPED,
                    records_fetched=0,
                    error_message="No news articles returned",
                )

            # Validate articles
            report = self._validator.validate_news(f"news-{symbol}", articles)
            if report.result == ValidationResult.INVALID:
                raise DataValidationError(f"Validation failed: {report.summary()}")

            # Store articles
            stored = 0
            for article in articles:
                stored += self._news_repo.add_articles([article], article.provider)

            # Fetch and store sentiment for each article
            for article in articles:
                sentiment = await self._news_adapter.fetch_sentiment(article)
                self._news_repo.add_sentiments([sentiment], article.provider)

            return IngestionResult(
                dataset_id=f"news-{symbol}-{int(time.time())}",
                provider_name=articles[0].provider if articles else "unknown",
                result_type=IngestionResultType.SUCCESS,
                records_fetched=len(articles),
                records_validated=len(articles),
                records_stored=len(articles),
                validation_report=report.summary() if report else None,
            )

        except DataValidationError as exc:
            self._logger.warning("Validation failed for news %s: %s", symbol, exc)
            return IngestionResult(
                dataset_id=f"news-{symbol}-{int(time.time())}",
                provider_name="unknown",
                result_type=IngestionResultType.QUARANTINED,
                error_message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("News ingestion failed for %s", symbol)
            return IngestionResult(
                dataset_id=f"news-{symbol}-{int(time.time())}",
                provider_name="unknown",
                result_type=IngestionResultType.FAILED,
                error_message=str(exc),
            )

    async def ingest_historical_market_data(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start_date: date,
        end_date: date,
        *,
        batch_size: int | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> "BatchIngestionResult":
        """Ingest historical market data for multiple symbols in batches.

        Args:
            symbols: List of symbols to ingest
            timeframe: Candle timeframe
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            batch_size: Override default batch size
            progress_callback: Optional callback(symbol_index, total, current_symbol)
        """
        from aios.providers.adapter import BatchIngestionResult

        bs = batch_size or self._config.batch_size
        rate_limit = self._config.rate_limit_ms / 1000.0 if self._config.rate_limit_ms else 0
        max_concurrent = self._config.max_concurrent

        results = BatchIngestionResult(total_symbols=len(symbols))

        # Process in batches to control memory and rate
        for i in range(0, len(symbols), bs):
            batch = symbols[i : i + bs]
            batch_results = await self._ingest_market_batch(
                batch,
                timeframe,
                start_date,
                end_date,
                rate_limit=rate_limit,
                max_concurrent=max_concurrent,
                progress_callback=progress_callback,
            )
            for r in batch_results.results:
                results.add_result(r)

            if progress_callback:
                progress_callback(min(i + bs, len(symbols)), len(symbols), batch[-1])

        return results

    async def _ingest_market_batch(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start_date: date,
        end_date: date,
        *,
        rate_limit: float = 0,
        max_concurrent: int = 1,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> "BatchIngestionResult":
        """Internal batch ingestion with concurrency and rate limiting."""
        from aios.providers.adapter import BatchIngestionResult

        semaphore = asyncio.Semaphore(max_concurrent)
        results = BatchIngestionResult(total_symbols=len(symbols))

        async def ingest_one(symbol: str) -> "IngestionResult":
            async with semaphore:
                if rate_limit > 0:
                    await asyncio.sleep(rate_limit)
                start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
                end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
                return await self.ingest_market_data(
                    symbol, timeframe, start=start_dt, end=end_dt
                )

        tasks = [ingest_one(s) for s in symbols]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.add_result(result)

        return results

    async def ingest_historical_shariah_data(
        self,
        symbols: list[str],
        *,
        batch_size: int | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> "BatchIngestionResult":
        """Ingest historical Shariah compliance for multiple symbols."""
        from aios.providers.adapter import BatchIngestionResult

        bs = batch_size or self._config.batch_size
        results = BatchIngestionResult(total_symbols=len(symbols))

        for i in range(0, len(symbols), bs):
            batch = symbols[i : i + bs]
            for j, symbol in enumerate(batch):
                result = await self.ingest_shariah_data(symbol)
                results.add_result(result)

            if progress_callback:
                progress_callback(min(i + bs, len(symbols)), len(symbols), batch[-1])

        return results

    async def ingest_historical_fundamentals(
        self,
        symbols: list[str],
        *,
        batch_size: int | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> "BatchIngestionResult":
        """Ingest historical fundamentals for multiple symbols."""
        from aios.providers.adapter import BatchIngestionResult

        bs = batch_size or self._config.batch_size
        results = BatchIngestionResult(total_symbols=len(symbols))

        for i in range(0, len(symbols), bs):
            batch = symbols[i : i + bs]
            for j, symbol in enumerate(batch):
                result = await self.ingest_fundamentals(symbol)
                results.add_result(result)

            if progress_callback:
                progress_callback(min(i + bs, len(symbols)), len(symbols), batch[-1])

        return results

    # -- Configuration and Status --

    @property
    def config(self) -> IngestionConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        return any(
            [
                self._market_adapter and self._market_repo,
                self._shariah_adapter and self._shariah_repo,
                self._fundamental_adapter and self._fundamental_repo,
                self._news_adapter and self._news_repo,
            ]
        )

    def get_adapter_status(self) -> dict[str, bool]:
        """Return which adapters are configured."""
        return {
            "market": self._market_adapter is not None and self._market_repo is not None,
            "shariah": self._shariah_adapter is not None and self._shariah_repo is not None,
            "fundamental": self._fundamental_adapter is not None
            and self._fundamental_repo is not None,
            "news": self._news_adapter is not None
            and self._news_repo is not None,
        }