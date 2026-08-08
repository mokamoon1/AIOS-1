"""Market repository (AIOS-606, AIOS-507).

Appends historical candle records immutably and serves AIOS standard market
models to the Data Layer. Duplicate ingestion of the same (symbol, timeframe,
timestamp) is prevented by the unique constraint (ADR-0006 section 5.5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select

from aios.data.models import Candle, Security, Timeframe
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import MarketCandleModel, SecurityModel
from aios.database.repositories.base import BaseRepository


def _candle_key(candle: Candle) -> tuple[str, Timeframe, datetime]:
    """Return a dialect-independent unique key for a candle.

    SQLite stores naive datetimes while the domain model is UTC-aware, so
    both sides are normalized to naive UTC before comparison.
    """
    timestamp = candle.timestamp
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    return (candle.symbol, candle.timeframe, timestamp)


class MarketRepository(BaseRepository[MarketCandleModel]):
    """Repository for market data (candles and securities).

    The primary entity is the immutable historical candle (AIOS-507).
    """

    entity_type = MarketCandleModel

    def add_candles(self, candles: list[Candle], provider: str) -> int:
        """Append candles, skipping keys already stored.

        Returns the number of newly stored rows. Historical records are
        never overwritten (AIOS-505, AIOS-507).
        """
        if not candles:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            existing: set[tuple[str, Timeframe, datetime]] = set()
            for symbol, timeframe, timestamp in session.execute(
                select(
                    MarketCandleModel.symbol,
                    MarketCandleModel.timeframe,
                    MarketCandleModel.timestamp,
                )
            ).all():
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
                existing.add((symbol, timeframe, timestamp))
            for candle in candles:
                if _candle_key(candle) in existing:
                    continue
                session.add(
                    MarketCandleModel(
                        timestamp=candle.timestamp,
                        symbol=candle.symbol,
                        timeframe=candle.timeframe,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        vwap=candle.vwap,
                        trade_count=candle.trade_count,
                        average_price=candle.average_price,
                        provider=provider,
                    )
                )
                stored += 1
        return stored

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        """Return candles ordered by timestamp (AIOS-507 lookup contract)."""
        statement = (
            select(MarketCandleModel)
            .where(
                MarketCandleModel.symbol == symbol,
                MarketCandleModel.timeframe == timeframe,
            )
            .order_by(MarketCandleModel.timestamp)
            .limit(limit)
        )
        if start is not None:
            statement = statement.where(MarketCandleModel.timestamp >= start)
        if end is not None:
            statement = statement.where(MarketCandleModel.timestamp <= end)
        return [cast(MarketCandleModel, row).to_domain() for row in self._scalars(statement)]

    def add_security(self, security: Security) -> None:
        """Persist a security entity (idempotent per symbol/exchange)."""
        with session_scope(self._session_factory) as session:
            existing = session.execute(
                select(SecurityModel).where(
                    SecurityModel.symbol == security.symbol,
                    SecurityModel.exchange == security.exchange,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return
            session.add(
                SecurityModel(
                    symbol=security.symbol,
                    exchange=security.exchange,
                    asset_type=security.asset_type,
                    currency=security.currency,
                    trading_session=security.trading_session,
                    timezone=security.timezone,
                    market_status=security.market_status,
                )
            )

    def get_security(self, symbol: str, exchange: str) -> Security:
        """Return the security domain model or raise :class:`RecordNotFoundError`."""
        row = self._first(
            select(SecurityModel).where(
                SecurityModel.symbol == symbol,
                SecurityModel.exchange == exchange,
            )
        )
        if row is None:
            raise RecordNotFoundError(f"Security {symbol!r} on {exchange!r} not found")
        return cast(SecurityModel, row).to_domain()
