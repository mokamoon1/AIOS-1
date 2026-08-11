"""News Intelligence interface tests (AIOS-005 section 7, AIOS-102 section 9)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aios.analysis.news import (
    NeutralNewsIntelligence,
    NewsArticle,
    SentimentEvaluation,
    SentimentLabel,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc


def _article(symbols: list[str] | None = None) -> NewsArticle:
    return NewsArticle(
        provider="test-provider",
        article_id="art-1",
        published_at=datetime(2026, 8, 1, 12, 0, tzinfo=_UTC),
        source="Test Wire",
        headline="Company announces results",
        summary="Quarterly results released.",
        url="https://example.com/art-1",
        symbols=symbols or ["AAPL"],
    )


class TestNewsArticle:
    def test_constructs(self) -> None:
        article = _article()
        assert article.provider == "test-provider"
        assert article.symbols == ["AAPL"]
        assert article.summary == "Quarterly results released."

    def test_empty_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NewsArticle(
                provider="",
                article_id="art-1",
                published_at=datetime(2026, 8, 1, tzinfo=_UTC),
                source="Test Wire",
                headline="Headline",
            )
        with pytest.raises(ValidationError):
            NewsArticle(
                provider="test-provider",
                article_id="art-1",
                published_at=datetime(2026, 8, 1, tzinfo=_UTC),
                source="Test Wire",
                headline=" ",
            )

    def test_empty_symbol_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _article(symbols=["AAPL", " "])

    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NewsArticle(
                provider="test-provider",
                article_id="art-1",
                published_at=datetime(2026, 8, 1, tzinfo=_UTC),
                source="Test Wire",
                headline="Headline",
                bogus=True,
            )


class TestSentimentEvaluation:
    def test_defaults_to_neutral(self) -> None:
        evaluation = SentimentEvaluation(provider="test-provider", article_id="art-1")
        assert evaluation.sentiment is SentimentLabel.NEUTRAL
        assert evaluation.score is None
        assert evaluation.methodology == "none"

    def test_sentiment_labels_exist(self) -> None:
        labels = list(SentimentLabel)
        assert SentimentLabel.BULLISH in labels
        assert SentimentLabel.BEARISH in labels
        assert SentimentLabel.NEUTRAL in labels
        assert len(labels) == 3

    def test_provider_score_passes_through_uninterpreted(self) -> None:
        evaluation = SentimentEvaluation(
            provider="test-provider",
            article_id="art-1",
            score=0.75,
            methodology="provider-lexicon",
        )
        assert evaluation.score == 0.75
        assert evaluation.methodology == "provider-lexicon"

    def test_empty_provider_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SentimentEvaluation(provider=" ", article_id="art-1")


class TestNeutralNewsIntelligence:
    def test_collect_returns_no_articles(self) -> None:
        intelligence = NeutralNewsIntelligence()
        assert intelligence.collect(["AAPL"]) == []

    def test_evaluate_is_neutral(self) -> None:
        intelligence = NeutralNewsIntelligence()
        evaluation = intelligence.evaluate(_article())
        assert evaluation.sentiment is SentimentLabel.NEUTRAL
        assert evaluation.score is None
        assert evaluation.provider == "test-provider"
        assert evaluation.article_id == "art-1"

    def test_explain_is_neutral_report(self) -> None:
        intelligence = NeutralNewsIntelligence()
        report = intelligence.explain(_article())
        assert "art-1" in report
        assert "test-provider" in report
        assert "AAPL" in report
        assert "neutral" in report

    def test_satisfies_protocol(self) -> None:
        from aios.analysis.news import NewsIntelligence

        assert isinstance(NeutralNewsIntelligence(), NewsIntelligence)
