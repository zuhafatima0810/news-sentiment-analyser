"""
src/fetcher.py
--------------
News headline fetcher for the News Headline Sentiment Analyser.

Provides :class:`NewsAPIFetcher`, which retrieves headlines from the
`NewsAPI <https://newsapi.org>`_ ``/v2/everything`` endpoint with exponential
back-off retry on rate-limit (HTTP 429) responses.

When no valid API key is configured the fetcher falls back transparently to
scraping the Google News RSS feed with BeautifulSoup / lxml, returning the
same dict structure so the rest of the pipeline is unaffected.
"""

import logging
import time
import json
from typing import List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"
_GOOGLE_RSS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
)
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


class NewsAPIFetcher:
    """Fetches news headlines from NewsAPI with rate-limit handling.

    If the supplied *api_key* is ``"YOUR_API_KEY"`` or empty the fetcher
    automatically falls back to scraping the Google News RSS feed.

    Args:
        api_key: NewsAPI authentication key.
        query: Search query string.
        page_size: Maximum number of articles to request (1-100).
        sources: Comma-separated list of NewsAPI source IDs (optional).
    """

    def __init__(
        self,
        api_key: str,
        query: str,
        page_size: int,
        sources: str = "",
    ) -> None:
        """Initialise the fetcher with connection parameters."""
        self.api_key = api_key
        self.query = query
        self.page_size = min(max(1, page_size), 100)
        self.sources = sources

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self) -> List[dict]:
        """Fetch headlines and return a normalised list of article dicts.

        Each dict contains:
            - ``title`` (str)
            - ``url`` (str)
            - ``publishedAt`` (str)
            - ``source`` (str)

        Returns:
            List of article dicts.  An empty list is returned on
            unrecoverable errors.
        """
        if not self.api_key or self.api_key == "YOUR_API_KEY":
            logger.info(
                "No valid NewsAPI key – falling back to Google News RSS scrape."
            )
            return self._fetch_rss()

        return self._fetch_newsapi()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_newsapi(self) -> List[dict]:
        """Call the NewsAPI /v2/everything endpoint with retry logic."""
        params: dict = {
            "q": self.query,
            "pageSize": self.page_size,
            "apiKey": self.api_key,
            "language": "en",
        }
        if self.sources:
            params["sources"] = self.sources

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = requests.get(
                    _NEWSAPI_ENDPOINT, params=params, timeout=15
                )

                if response.status_code == 429:
                    wait = _BACKOFF_BASE ** attempt
                    logger.warning(
                        "NewsAPI rate-limit hit (attempt %d/%d). "
                        "Retrying in %ds.",
                        attempt,
                        _MAX_RETRIES,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()

                try:
                    data = response.json()
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error("Failed to decode NewsAPI JSON response: %s", exc)
                    return []

                articles = data.get("articles", [])
                logger.info(
                    "NewsAPI returned %d articles for query '%s'.",
                    len(articles),
                    self.query,
                )
                return self._normalise_newsapi(articles)

            except requests.HTTPError as exc:
                logger.error("HTTP error from NewsAPI: %s", exc)
                return []
            except requests.RequestException as exc:
                logger.error("Network error fetching from NewsAPI: %s", exc)
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE ** attempt
                    logger.info("Retrying in %ds (attempt %d/%d).", wait, attempt, _MAX_RETRIES)
                    time.sleep(wait)

        logger.error("All %d NewsAPI attempts exhausted.", _MAX_RETRIES)
        return []

    @staticmethod
    def _normalise_newsapi(articles: list) -> List[dict]:
        """Convert raw NewsAPI article dicts to the standard schema."""
        normalised: List[dict] = []
        for art in articles:
            title = art.get("title") or ""
            if not title or title == "[Removed]":
                continue
            normalised.append(
                {
                    "title": title,
                    "url": art.get("url") or "",
                    "publishedAt": art.get("publishedAt") or "",
                    "source": (art.get("source") or {}).get("name") or "",
                }
            )
        return normalised

    def _fetch_rss(self) -> List[dict]:
        """Scrape Google News RSS and return articles in the standard schema."""
        url = _GOOGLE_RSS_TEMPLATE.format(query=quote_plus(self.query))
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch Google News RSS: %s", exc)
            return []

        try:
            soup = BeautifulSoup(response.content, "lxml-xml")
        except Exception as exc:
            logger.error("Failed to parse Google News RSS XML: %s", exc)
            return []

        items = soup.find_all("item")
        logger.info(
            "Google News RSS returned %d items for query '%s'.",
            len(items),
            self.query,
        )

        articles: List[dict] = []
        for item in items[: self.page_size]:
            title_tag = item.find("title")
            link_tag = item.find("link")
            pub_tag = item.find("pubDate")
            source_tag = item.find("source")

            articles.append(
                {
                    "title": title_tag.get_text(strip=True) if title_tag else "",
                    "url": link_tag.get_text(strip=True) if link_tag else "",
                    "publishedAt": pub_tag.get_text(strip=True) if pub_tag else "",
                    "source": source_tag.get_text(strip=True) if source_tag else "Google News",
                }
            )
        return articles


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def get_headlines(config) -> List[dict]:
    """Fetch headlines using settings from *config*.

    Args:
        config: Module or object exposing ``NEWS_API_KEY``, ``QUERY``,
                ``PAGE_SIZE``, and ``SOURCES`` attributes.

    Returns:
        List of article dicts (see :meth:`NewsAPIFetcher.fetch`).
    """
    fetcher = NewsAPIFetcher(
        api_key=config.NEWS_API_KEY,
        query=config.QUERY,
        page_size=config.PAGE_SIZE,
        sources=getattr(config, "SOURCES", ""),
    )
    return fetcher.fetch()
