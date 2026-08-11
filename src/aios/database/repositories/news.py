"""News repository (AIOS-606, Phase 9.1).

Stores and retrieves news articles and sentiment evaluations.
Historical records are immutable: repositories append new rows instead of
overwriting existing ones (AIOS-505, AIOS-507).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select

from aios.analysis.news import NewsArticle, SentimentEvaluation
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import NewsArticleModel, NewsSentimentModel
from aios.database.repositories.base import BaseRepository


def _utc(value: datetime) -> datetime:
    """Normalize a database datetime to a UTC-aware datetime.

    SQLite returns naive datetimes regardless of the declared column type;
    domain models require UTC timestamps, so an explicit UTC time zone is
    attached here to keep round trips consistent.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class NewsRepository(BaseRepository[NewsArticleModel]):
    """Repository for news articles and sentiment evaluations."""

    entity_type = NewsArticleModel

    def add_articles(self, articles: list[NewsArticle], provider: str) -> int:
        """Append news articles, skipping keys already stored.

        Returns the number of newly stored rows. Historical records are
        never overwritten (AIOS-505, AIOS-507).
        """
        if not articles:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            existing: set[tuple[str, str]] = set()
            for provider_name, article_id in session.execute(
                select(
                    NewsArticleModel.provider,
                    NewsArticleModel.article_id,
                )
            ).all():
                existing.add((provider_name, article_id))
            for article in articles:
                if (provider, article.article_id) in existing:
                    continue
                session.add(
                    NewsArticleModel(
                        provider=provider,
                        article_id=article.article_id,
                        published_at=article.published_at,
                        retrieved_at=article.retrieved_at,
                        source=article.source,
                        headline=article.headline,
                        summary=article.summary,
                        url=article.url,
                        symbols=article.symbols,
                    )
                )
                stored += 1
        return stored

    def get_articles(
        self,
        symbol: str | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsArticle]:
        """Return articles ordered by published_at (newest first)."""
        statement = select(NewsArticleModel).order_by(NewsArticleModel.published_at.desc()).limit(limit)
        if symbol is not None:
            # Filter by symbols array containing the symbol
            # For SQLite, we use LIKE on the JSON array
            statement = statement.where(NewsArticleModel.symbols.like(f'%"{symbol}"%'))
        if start is not None:
            statement = statement.where(NewsArticleModel.published_at >= start)
        if end is not None:
            statement = statement.where(NewsArticleModel.published_at <= end)
        return [cast(NewsArticleModel, row).to_domain() for row in self._scalars(statement)]

    def add_sentiments(self, evaluations: list[SentimentEvaluation], provider: str) -> int:
        """Append sentiment evaluations as new immutable rows."""
        if not evaluations:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            for evaluation in evaluations:
                session.add(
                    NewsSentimentModel(
                        provider=provider,
                        article_id=evaluation.article_id,
                        sentiment=evaluation.sentiment.value if hasattr(evaluation.sentiment, 'value') else evaluation.sentiment,
                        score=evaluation.score,
                        methodology=evaluation.methodology,
                        evaluated_at=evaluation.evaluated_at,
                    )
                )
                stored += 1
        return stored

    def get_sentiment(self, article_id: str) -> SentimentEvaluation | None:
        """Return the latest sentiment evaluation for an article."""
        statement = (
            select(NewsSentimentModel)
            .where(NewsSentimentModel.article_id == article_id)
            .order_by(NewsSentimentModel.evaluated_at.desc())
            .limit(1)
        )
        row = self._first(statement)
        if row is None:
            return None
        return cast(NewsSentimentModel, row).to_domain()

    def get_sentiment_history(
        self, article_id: str, *, since: datetime | None = None
    ) -> list[SentimentEvaluation]:
        """Return sentiment history for an article."""
        statement = select(NewsSentimentModel).where(NewsSentimentModel.article_id == article_id)
        if since is not None:
            statement = statement.where(NewsSentimentModel.evaluated_at >= since)
        return [
            cast(NewsSentimentModel, row).to_domain()
            for row in self._scalars(
                statement.order_by(NewsSentimentModel.evaluated_at.desc())
            )
        ]