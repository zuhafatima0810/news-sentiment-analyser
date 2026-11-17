"""
src/analyser.py
---------------
Sentiment analysis engine for the News Headline Sentiment Analyser.

Uses two complementary libraries:

* **TextBlob** – provides polarity (−1 to +1) and subjectivity (0 to 1).
* **VADER** (``vaderSentiment``) – rule-based, tuned for short social-media /
  news text; provides compound, positive, negative, and neutral scores.

The ``label`` field is derived from the VADER compound score:

* compound ≥ 0.05  → ``"positive"``
* compound ≤ −0.05 → ``"negative"``
* otherwise        → ``"neutral"``
"""

import logging
from typing import List

from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class SentimentAnalyser:
    """Dual-engine sentiment analyser (TextBlob + VADER).

    Instantiate once and reuse across many calls – both underlying models are
    loaded at construction time.
    """

    def __init__(self) -> None:
        """Load the VADER ``SentimentIntensityAnalyzer`` (TextBlob is stateless)."""
        self._vader = SentimentIntensityAnalyzer()
        logger.debug("SentimentAnalyser initialised (TextBlob + VADER).")

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyse(self, text: str) -> dict:
        """Analyse *text* and return a combined sentiment dict.

        Args:
            text: The string to analyse (typically a news headline).

        Returns:
            A dict with the following keys:

            * ``textblob_polarity`` (float) – TextBlob polarity score.
            * ``textblob_subjectivity`` (float) – TextBlob subjectivity.
            * ``vader_compound`` (float) – VADER compound score.
            * ``vader_pos`` (float) – VADER positive ratio.
            * ``vader_neg`` (float) – VADER negative ratio.
            * ``vader_neu`` (float) – VADER neutral ratio.
            * ``label`` (str) – ``"positive"``, ``"negative"``, or
              ``"neutral"`` derived from the VADER compound score.
        """
        if not text:
            return self._empty_result()

        # TextBlob
        blob = TextBlob(text)
        tb_polarity: float = blob.sentiment.polarity
        tb_subjectivity: float = blob.sentiment.subjectivity

        # VADER
        vader_scores = self._vader.polarity_scores(text)
        compound: float = vader_scores["compound"]

        label: str
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        return {
            "textblob_polarity": round(tb_polarity, 4),
            "textblob_subjectivity": round(tb_subjectivity, 4),
            "vader_compound": round(compound, 4),
            "vader_pos": round(vader_scores["pos"], 4),
            "vader_neg": round(vader_scores["neg"], 4),
            "vader_neu": round(vader_scores["neu"], 4),
            "label": label,
        }

    def analyse_headlines(self, articles: List[dict]) -> List[dict]:
        """Enrich a list of article dicts with sentiment information.

        Each dict in *articles* gains a ``"sentiment"`` key containing the
        output of :meth:`analyse` applied to the article's ``"title"`` field.

        Args:
            articles: List of article dicts (must contain a ``"title"`` key).

        Returns:
            The same list with ``"sentiment"`` dicts injected in-place
            (a copy of each article dict is made to avoid mutating the input).
        """
        enriched: List[dict] = []
        for article in articles:
            title = article.get("title", "")
            sentiment = self.analyse(title)
            enriched_article = dict(article)
            enriched_article["sentiment"] = sentiment
            enriched.append(enriched_article)
            logger.debug(
                "Analysed: '%s' → %s (compound=%.4f)",
                title[:60],
                sentiment["label"],
                sentiment["vader_compound"],
            )
        logger.info("Analysed %d headlines.", len(enriched))
        return enriched

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result() -> dict:
        """Return a zeroed sentiment dict for empty / missing text."""
        return {
            "textblob_polarity": 0.0,
            "textblob_subjectivity": 0.0,
            "vader_compound": 0.0,
            "vader_pos": 0.0,
            "vader_neg": 0.0,
            "vader_neu": 1.0,
            "label": "neutral",
        }


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def analyse_all(articles: List[dict]) -> List[dict]:
    """Analyse sentiment for all *articles* using a fresh :class:`SentimentAnalyser`.

    Args:
        articles: List of article dicts (each must have a ``"title"`` key).

    Returns:
        Enriched list with ``"sentiment"`` dicts added to each article.
    """
    analyser = SentimentAnalyser()
    return analyser.analyse_headlines(articles)
