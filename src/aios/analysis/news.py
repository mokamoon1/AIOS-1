"""News Intelligence interfaces (AIOS-005 section 7, AIOS-102 section 9).

Phase 3 includes News Intelligence: news collection, event analysis, and
sentiment evaluation (AIOS-005 section 7). The News Intelligence Agent collects
important news, detects company events, and evaluates market impact (AIOS-102
section 9, AIOS-004 section 2).

News data sources and sentiment scoring are not yet documented or approved
(AIOS-303 section 14, AIOS-502 section 15), and AIOS must never use an
unapproved data source or fabricate missing data (AIOS-502 sections 1 and 12).
This module therefore provides the standardized interfaces and the neutral
evaluation only: AIOS attaches no opinion to an article and computes no
sentiment score, so no scoring methodology or threshold is invented here. The
default evaluation is ``NEUTRAL`` and any score is carried as an uninterpreted,
provider-supplied value with provenance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SentimentLabel(str, Enum):
    """Sentiment label assigned by AIOS (AIOS-102 section 9).

    AIOS assigns sentiment labels based on rule-based evaluation.
    """
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class NewsArticle(BaseModel):
    """Standardized news article (AIOS-102 section 9, AIOS-005 section 7).

    Carries provider provenance so the origin of every news item is preserved
    (AIOS-502 sections 1 and 14). No news data source is approved yet, so no
    acquisition is wired; this model standardizes the shape future providers
    must produce through the Data Layer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    article_id: str
    published_at: datetime
    retrieved_at: datetime = Field(default_factory=_utc_now)
    source: str
    headline: str
    summary: str | None = None
    url: str | None = None
    symbols: list[str] = Field(default_factory=list)

    @field_validator("provider", "article_id", "source", "headline")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @field_validator("symbols")
    @classmethod
    def symbols_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if any(not symbol.strip() for symbol in value):
            raise ValueError("symbols must not be empty")
        return value


class SentimentEvaluation(BaseModel):
    """Sentiment evaluation for a news article (AIOS-102 section 9).

    AIOS computes sentiment score using rule-based evaluation methodology.
    The evaluation includes sentiment label, confidence score, and evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    article_id: str
    sentiment: SentimentLabel = SentimentLabel.NEUTRAL
    score: float | None = None
    methodology: str = "none"
    evaluated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("provider", "article_id", "methodology")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


@runtime_checkable
class NewsIntelligence(Protocol):
    """News Intelligence interface (AIOS-005 section 7, AIOS-102 section 9).

    Implementations collect news, analyze company events, and evaluate market
    impact using the standardized models. Phase 3 provides this interface and
    the :class:`NeutralNewsIntelligence` implementation; no data source or
    scoring methodology is approved, so nothing beyond neutral evaluation is
    wired.
    """

    def collect(self, symbols: list[str]) -> list[NewsArticle]:
        """Collect news articles for the requested symbols."""
        ...

    def evaluate(self, article: NewsArticle) -> SentimentEvaluation:
        """Evaluate the sentiment of a single article."""
        ...

    def explain(self, article: NewsArticle) -> str:
        """Produce an explainable analysis report for a single article."""
        ...


class NeutralNewsIntelligence:
    """Neutral News Intelligence implementation (AIOS-005 section 7).

    Collects nothing because no news data source is approved (AIOS-502
    section 15) and evaluates every article as neutral, documenting the
    provenance and the absence of an approved scoring methodology in the
    explainable report.
    """

    def collect(self, symbols: list[str]) -> list[NewsArticle]:
        """Return no articles: no news data source is approved (AIOS-502)."""
        return []

    def evaluate(self, article: NewsArticle) -> SentimentEvaluation:
        """Return the neutral evaluation for ``article`` (AIOS-102 section 9)."""
        return SentimentEvaluation(
            provider=article.provider,
            article_id=article.article_id,
            sentiment=SentimentLabel.NEUTRAL,
            score=None,
            methodology="neutral",
            evaluated_at=_utc_now(),
        )

    def explain(self, article: NewsArticle) -> str:
        """Return an explainable report with a neutral market impact statement."""
        symbols = ", ".join(article.symbols) if article.symbols else "no symbol"
        return (
            f"News article {article.article_id!r} from {article.provider} published at "
            f"{article.published_at.isoformat()} on {article.source!r} relates to {symbols}. "
            f"Market impact is not assessed: news sentiment scoring is not an approved "
            f"methodology (AIOS-303 section 14, AIOS-502 section 15), so the evaluation "
            f"is {SentimentLabel.NEUTRAL.value}."
        )
