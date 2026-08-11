"""News Intelligence Engine (AIOS-005 Section 7, Phase 9.1).

The News Intelligence Engine orchestrates the complete news analysis pipeline:
fetching news via providers/adapters, validating, normalizing, and performing
intelligence analysis (relevance, sentiment, confidence) to produce structured
NewsIntelligenceOutput for consumption by the Signal Engine.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aios.analysis.models import (
    ConfidenceScore,
    Evidence,
    Explanation,
    NewsIntelligenceOutput,
    RelevanceAssessment,
    SentimentAssessment,
)
from aios.analysis.news import NewsArticle, SentimentEvaluation, SentimentLabel

if TYPE_CHECKING:
    from aios.providers.adapter import NewsDataAdapter


# Positive and negative keyword lists for rule-based sentiment analysis
_POSITIVE_KEYWORDS = frozenset({
    "strong", "growth", "exceeds", "announces", "new", "record", "beats",
    "surges", "rises", "gains", "profit", "revenue up", "earnings beat",
    "outperform", "upgrade", "buyback", "dividend increase", "partnership",
    "acquisition", "merger", "expansion", "launch", "breakthrough",
    "approval", "milestone", "record high", "all-time high", "bullish",
})

_NEGATIVE_KEYWORDS = frozenset({
    "weak", "decline", "loss", "misses", "cut", "layoff", "downturn",
    "falls", "drops", "slips", "losses", "revenue down", "earnings miss",
    "underperform", "downgrade", "sell-off", "dividend cut", "investigation",
    "lawsuit", "recall", "bankruptcy", "default", "restructuring",
    "contraction", "recession", "bearish", "crash", "plunge",
})


class NewsEngine:
    """News Intelligence Engine (Phase 9.1).

    Orchestrates the complete news analysis pipeline:
    1. Fetch news via provider adapters
    2. Validate and normalize articles
    3. Assess relevance to symbols
    4. Analyze sentiment with evidence
    3. Calculate confidence with rationale
    4. Generate evidence and explanations
    4. Produce structured NewsIntelligenceOutput

    The engine uses provider adapters for data fetching and delegates
    storage to the IngestionService/Repository layer.
    """

    def __init__(
        self,
        news_adapter: "NewsDataAdapter",
        *,
        logger: logging.Logger | None = None,
        relevance_threshold: float = 0.3,
        sentiment_threshold: float = 0.1,
        confidence_threshold: float = 0.5,
    ) -> None:
        self._adapter = news_adapter
        self._logger = logger or logging.getLogger("aios.analysis.news_engine")
        self._relevance_threshold = relevance_threshold
        self._sentiment_threshold = sentiment_threshold
        self._confidence_threshold = confidence_threshold

        # Keyword weights for relevance scoring
        self._symbol_weight = 0.5
        self._headline_weight = 0.3
        self._summary_weight = 0.2

    # --- Public API ---

    async def analyze_article(
        self,
        article: NewsArticle,
        symbol: str,
        *,
        evaluation_time: datetime | None = None,
    ) -> NewsIntelligenceOutput:
        """Analyze a single news article and produce structured intelligence output.

        This is the main entry point for the News Intelligence Engine.
        """
        self._logger.info("Analyzing article %s for symbol %s", article.article_id, symbol)

        # 1. Validate the article
        self._validate_article(article)

        # 2. Normalize the article
        normalized = self._normalize_article(article)

        # 3. Assess relevance
        relevance = self._assess_relevance(normalized, symbol)

        # Skip sentiment analysis if relevance is below threshold
        if relevance.score < self._relevance_threshold:
            self._logger.info(
                "Article %s below relevance threshold for %s (score: %.2f)",
                article.article_id, symbol, relevance.score
            )
            return self._create_output(
                article, symbol, relevance,
                self._create_neutral_sentiment(article),
                ConfidenceScore(score=0.0, rationale="Below relevance threshold", factors=["low_relevance"]),
                [], self._create_low_relevance_explanation(article, symbol)
            )

        # 4. Analyze sentiment
        sentiment = self._analyze_sentiment(normalized, evaluation_time=evaluation_time)

        # 5. Calculate confidence
        confidence = self._calculate_confidence(normalized, relevance, sentiment)

        # 6. Collect evidence
        evidence = self._collect_evidence(normalized, relevance, sentiment)

        # 7. Generate explanation
        explanation = self._generate_explanation(normalized, relevance, sentiment)

        return self._create_output(
            article, symbol, relevance, sentiment,
            ConfidenceScore(
                score=confidence,
                rationale=self._confidence_rationale(relevance, sentiment),
                factors=self._confidence_factors(relevance, sentiment)
            ),
            evidence, explanation
        )

    async def analyze_symbol_news(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        evaluation_time: datetime | None = None,
    ) -> list[NewsIntelligenceOutput]:
        """Fetch and analyze all news for a symbol.

        Returns a list of NewsIntelligenceOutput sorted by relevance (descending).
        """
        self._logger.info("Fetching and analyzing news for %s", symbol)

        articles = await self._adapter.fetch_news([symbol], start=start, end=end, limit=limit)
        self._logger.info("Fetched %d articles for %s", len(articles), symbol)

        results = []
        for article in articles:
            try:
                output = await self.analyze_article(article, symbol, evaluation_time=evaluation_time)
                results.append(output)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Failed to analyze article %s: %s", article.article_id, exc)

        # Sort by relevance score descending
        results.sort(key=lambda x: x.relevance.score, reverse=True)
        return results

    # --- Internal Pipeline Methods ---

    def _validate_article(self, article: NewsArticle) -> None:
        """Validate article has required fields."""
        if not article.headline or not article.headline.strip():
            raise ValueError("Article headline is required")
        if not article.provider or not article.provider.strip():
            raise ValueError("Article provider is required")
        if not article.article_id or not article.article_id.strip():
            raise ValueError("Article ID is required")
        if article.published_at is None:
            raise ValueError("Published timestamp is required")
        if not article.symbols:
            raise ValueError("At least one symbol is required")

    def _normalize_article(self, article: NewsArticle) -> NewsArticle:
        """Normalize article text for analysis."""
        # In a full implementation, this might include:
        # - Text cleaning (HTML removal, whitespace normalization)
        # - Entity extraction
        # - Date normalization
        # For now, return as-is since mock articles are already clean
        return article

    def _assess_relevance(self, article: NewsArticle, symbol: str) -> RelevanceAssessment:
        """Assess relevance of article to the given symbol."""
        score = 0.0
        rationale_parts = []
        evidence = []

        # Check if symbol is explicitly mentioned in symbols list
        if symbol.upper() in [s.upper() for s in article.symbols]:
            score += self._symbol_weight
            rationale_parts.append(f"Symbol {symbol} explicitly listed in article symbols")
            evidence.append(f"Symbol {symbol} in article symbols list")

        # Check headline for symbol mentions
        headline_upper = article.headline.upper()
        symbol_upper = symbol.upper()
        if symbol_upper in headline_upper:
            score += self._headline_weight
            rationale_parts.append(f"Symbol {symbol} mentioned in headline")
            evidence.append(f"Symbol found in headline: '{article.headline[:100]}...'")

        # Check summary for symbol mentions
        if article.summary and symbol_upper in article.summary.upper():
            score += self._summary_weight
            rationale_parts.append(f"Symbol {symbol} mentioned in summary")
            evidence.append(f"Symbol found in summary: '{article.summary[:100]}...'")

        # Cap score at 1.0
        score = min(score, 1.0)

        if score == 0.0:
            rationale = f"No direct relevance to {symbol} found"
        else:
            rationale = "; ".join(rationale_parts)

        explanation = Explanation(
            summary=f"Relevance to {symbol}: {score:.2f}",
            factors=rationale_parts,
            methodology="rule_based_symbol_matching"
        )

        return RelevanceAssessment(
            score=score,
            rationale=rationale,
            evidence=evidence,
            explanation=explanation
        )

    def _analyze_sentiment(
        self,
        article: NewsArticle,
        *,
        evaluation_time: datetime | None = None,
    ) -> SentimentAssessment:
        """Analyze sentiment of article using rule-based approach."""
        headline = article.headline.lower()
        summary = (article.summary or "").lower()
        text = f"{headline} {summary}"

        positive_count = sum(1 for word in _POSITIVE_KEYWORDS if word in text)
        negative_count = sum(1 for word in _NEGATIVE_KEYWORDS if word in text)

        # Determine sentiment label
        if positive_count > negative_count:
            label = "BULLISH"
            base_score = min(0.3 + (positive_count - negative_count) * 0.15, 1.0)
        elif negative_count > positive_count:
            label = "BEARISH"
            base_score = max(-0.3 - (negative_count - positive_count) * 0.15, -1.0)
        else:
            label = "NEUTRAL"
            base_score = 0.0

        # Calculate confidence based on keyword count and text length
        total_keywords = positive_count + negative_count
        text_length = len(text.split())
        confidence = min(0.5 + total_keywords * 0.1 + text_length * 0.001, 1.0)

        # Collect evidence
        evidence = []
        matched_positive = [w for w in _POSITIVE_KEYWORDS if w in text]
        matched_negative = [w for w in _NEGATIVE_KEYWORDS if w in text]
        if matched_positive:
            evidence.append(Evidence(
                source="headline/summary",
                article_id="",
                facts=[f"Positive keywords: {', '.join(matched_positive)}"]
            ))
        if matched_negative:
            evidence.append(Evidence(
                source="headline/summary",
                article_id="",
                facts=[f"Negative keywords: {', '.join(matched_negative)}"]
            ))

        explanation = Explanation(
            summary=f"Sentiment: {label} (score: {base_score:.2f})",
            factors=[f"Positive keywords: {positive_count}", f"Negative keywords: {negative_count}"],
            methodology="rule_based_keyword_analysis"
        )

        # Determine label enum
        label_enum = SentimentLabel.BULLISH if label == "BULLISH" else (
            SentimentLabel.BEARISH if label == "BEARISH" else SentimentLabel.NEUTRAL
        )

        eval_time = evaluation_time or _utc_now()

        return SentimentAssessment(
            label=label,
            score=base_score,
            confidence=confidence,
            methodology="rule_based_keyword_analysis",
            evidence=evidence,
            explanation=Explanation(
                summary=f"Sentiment classified as {label} based on keyword analysis",
                factors=[f"Positive keywords: {positive_count}", f"Negative keywords: {negative_count}"],
                methodology="rule_based_keyword_analysis"
            ),
            evaluated_at=eval_time,
        )

    def _calculate_confidence(
        self,
        article: NewsArticle,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment
    ) -> float:
        """Calculate overall confidence in the intelligence assessment."""
        # Base confidence from relevance
        relevance_conf = relevance.score * 0.4

        # Sentiment confidence contribution
        sentiment_conf = sentiment.confidence * 0.3

        # Data completeness
        completeness = 0.3
        if not article.summary:
            completeness -= 0.1
        if not article.url:
            completeness -= 0.05

        confidence = relevance_conf + sentiment_conf + completeness
        return min(max(confidence, 0.0), 1.0)

    def _confidence_rationale(
        self,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment
    ) -> str:
        parts = []
        if relevance.score >= 0.5:
            parts.append(f"High relevance ({relevance.score:.2f})")
        else:
            parts.append(f"Low relevance ({relevance.score:.2f})")

        parts.append(f"Sentiment confidence: {sentiment.confidence:.2f}")

        return "; ".join(parts)

    def _confidence_factors(
        self,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment
    ) -> list[str]:
        factors = []
        if relevance.score >= 0.5:
            factors.append("high_relevance")
        else:
            factors.append("low_relevance")

        if sentiment.confidence >= 0.7:
            factors.append("high_sentiment_confidence")
        elif sentiment.confidence >= 0.4:
            factors.append("medium_sentiment_confidence")
        else:
            factors.append("low_sentiment_confidence")

        return factors

    def _collect_evidence(
        self,
        article: NewsArticle,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment
    ) -> list[Evidence]:
        evidence = []

        # Add relevance evidence
        for ev in relevance.evidence:
            evidence.append(Evidence(
                source="relevance_assessment",
                article_id=article.article_id,
                facts=[ev]
            ))

        # Add sentiment evidence
        evidence.extend(sentiment.evidence)

        return evidence

    def _generate_explanation(
        self,
        article: NewsArticle,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment
    ) -> Explanation:
        summary_parts = [
            f"Article '{article.headline[:80]}...' analyzed for {article.symbols[0] if article.symbols else 'unknown'}."
        ]

        if relevance.score >= 0.5:
            summary_parts.append(f"High relevance ({relevance.score:.2f}) to the symbol.")
        else:
            summary_parts.append(f"Low relevance ({relevance.score:.2f}) to the symbol.")

        summary_parts.append(f"Sentiment: {sentiment.label} ({sentiment.score:.2f}) with {sentiment.confidence:.0%} confidence.")

        factors = [
            f"Relevance: {relevance.score:.2f}",
            f"Sentiment: {sentiment.label} ({sentiment.score:.2f})",
            f"Sentiment confidence: {sentiment.confidence:.2f}",
        ]

        return Explanation(
            summary=" ".join(summary_parts),
            factors=summary_parts,
            methodology="rule_based_keyword_analysis_with_relevance_weighting"
        )

    def _create_neutral_sentiment(self, article: NewsArticle) -> SentimentAssessment:
        return SentimentAssessment(
            label="NEUTRAL",
            score=0.0,
            confidence=0.5,
            methodology="default_neutral",
            evidence=[],
            explanation=Explanation(
                summary="No sentiment analysis performed (below relevance threshold)",
                factors=["below_relevance_threshold"],
                methodology="default_neutral"
            ),
            evaluated_at=_utc_now(),
        )

    def _create_low_relevance_explanation(self, article: NewsArticle, symbol: str) -> Explanation:
        return Explanation(
            summary=f"Article '{article.headline[:80]}...' has low relevance to {symbol}. No sentiment analysis performed.",
            factors=["below_relevance_threshold"],
            methodology="relevance_filtering"
        )

    def _create_output(
        self,
        article: NewsArticle,
        symbol: str,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment,
        confidence: ConfidenceScore,
        evidence: list[Evidence],
        explanation: Explanation,
    ) -> NewsIntelligenceOutput:
        return NewsIntelligenceOutput(
            article_id=article.article_id,
            symbol=symbol,
            provider=article.provider,
            published_at=article.published_at,
            relevance=relevance,
            sentiment=sentiment,
            confidence=confidence,
            evidence=evidence,
            explanation=explanation,
        )

    def _confidence_rationale(
        self,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment
    ) -> str:
        parts = []
        if relevance.score >= 0.5:
            parts.append(f"High relevance ({relevance.score:.2f})")
        else:
            parts.append(f"Low relevance ({relevance.score:.2f})")

        parts.append(f"Sentiment confidence: {sentiment.confidence:.2f}")
        return "; ".join(parts)

    def _confidence_factors(
        self,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment
    ) -> list[str]:
        factors = []
        if relevance.score >= 0.5:
            factors.append("high_relevance")
        else:
            factors.append("low_relevance")

        if sentiment.confidence >= 0.7:
            factors.append("high_sentiment_confidence")
        elif sentiment.confidence >= 0.4:
            factors.append("medium_sentiment_confidence")
        else:
            factors.append("low_sentiment_confidence")

        return factors

    def _create_low_relevance_explanation(self, article: NewsArticle, symbol: str) -> Explanation:
        return Explanation(
            summary=f"Article '{article.headline[:80]}...' has low relevance to {symbol}. No sentiment analysis performed.",
            factors=["below_relevance_threshold"],
            methodology="relevance_filtering"
        )

    def _create_output(
        self,
        article: NewsArticle,
        symbol: str,
        relevance: RelevanceAssessment,
        sentiment: SentimentAssessment,
        confidence: ConfidenceScore,
        evidence: list[Evidence],
        explanation: Explanation,
    ) -> NewsIntelligenceOutput:
        return NewsIntelligenceOutput(
            article_id=article.article_id,
            symbol=symbol,
            provider=article.provider,
            published_at=article.published_at,
            relevance=relevance,
            sentiment=sentiment,
            confidence=confidence,
            evidence=evidence,
            explanation=explanation,
        )