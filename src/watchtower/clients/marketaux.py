"""Marketaux adapter with Watchtower-owned normalized headline records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx


class NewsClientError(RuntimeError):
    """Base error for failures at the news-provider boundary."""


class NewsAuthenticationError(NewsClientError):
    """Raised when the news provider rejects Watchtower's credentials."""


class NewsRateLimitError(NewsClientError):
    """Raised when the news provider has exhausted the request budget."""


class NewsRequestError(NewsClientError):
    """Raised when a news-provider request cannot be completed."""


class NewsPayloadError(NewsClientError):
    """Raised when the news provider returns an unusable response shape."""


@dataclass(frozen=True, slots=True)
class NewsHeadline:
    """Headline metadata normalized into Watchtower's internal representation."""

    ticker: str
    title: str
    snippet: str | None
    url: str
    published_at: datetime
    source: str


class MarketauxClient:
    """Retrieve ticker-specific financial headlines from Marketaux."""

    PROVIDER_NAME = "Marketaux"
    NEWS_URL = "https://api.marketaux.com/v1/news/all"
    FREE_PLAN_MAX_ARTICLES = 3

    def __init__(
        self,
        *,
        api_token: str,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        normalized_token = api_token.strip()
        if not normalized_token:
            raise ValueError("Marketaux API token must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("news timeout must be greater than zero")

        self._api_token = normalized_token
        self._timeout = timeout_seconds
        self._http = http_client or httpx.Client()
        self._owns_http_client = http_client is None

    def close(self) -> None:
        """Close the internally created HTTP client, if this instance owns it."""

        if self._owns_http_client:
            self._http.close()

    def __enter__(self) -> MarketauxClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_headlines(
        self,
        ticker: str,
        *,
        limit: int = FREE_PLAN_MAX_ARTICLES,
    ) -> list[NewsHeadline]:
        """Return up to ``limit`` recent English-language ticker headlines."""

        normalized_ticker = self._normalize_ticker(ticker)
        if not 1 <= limit <= self.FREE_PLAN_MAX_ARTICLES:
            raise ValueError(
                f"headline limit must be between 1 and {self.FREE_PLAN_MAX_ARTICLES}"
            )

        payload = self._get_json(
            params={
                "api_token": self._api_token,
                "symbols": normalized_ticker,
                "filter_entities": "true",
                "language": "en",
                "limit": limit,
            }
        )
        articles = self._extract_articles(payload)
        return [
            self._normalize_article(normalized_ticker, article) for article in articles
        ]

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise ValueError("ticker must not be empty")
        return normalized_ticker

    def _get_json(self, *, params: dict[str, str | int]) -> Any:
        try:
            response = self._http.get(
                self.NEWS_URL,
                params=params,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise NewsRequestError("news provider request failed") from exc

        if response.status_code in {401, 403}:
            raise NewsAuthenticationError("news provider rejected credentials")
        if response.status_code == 429:
            raise NewsRateLimitError("news provider rate limit reached")
        if response.is_error:
            raise NewsRequestError("news provider request failed")

        try:
            return response.json()
        except ValueError as exc:
            raise NewsPayloadError("news provider returned invalid JSON") from exc

    @staticmethod
    def _extract_articles(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            raise NewsPayloadError("news provider response must be an object")

        articles = payload.get("data")
        if not isinstance(articles, list) or not all(
            isinstance(article, dict) for article in articles
        ):
            raise NewsPayloadError("news provider response has invalid article data")
        return articles

    @classmethod
    def _normalize_article(
        cls,
        ticker: str,
        article: dict[str, Any],
    ) -> NewsHeadline:
        title = cls._required_string(article, "title")
        url = cls._required_string(article, "url")
        source = cls._required_string(article, "source")
        published_at = cls._parse_published_at(article.get("published_at"))

        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise NewsPayloadError("news provider returned an invalid article URL")

        raw_snippet = article.get("snippet")
        if raw_snippet is None:
            snippet = None
        elif isinstance(raw_snippet, str):
            snippet = raw_snippet.strip() or None
        else:
            raise NewsPayloadError("news provider returned an invalid article snippet")

        return NewsHeadline(
            ticker=ticker,
            title=title,
            snippet=snippet,
            url=url,
            published_at=published_at,
            source=source,
        )

    @staticmethod
    def _required_string(article: dict[str, Any], field: str) -> str:
        value = article.get(field)
        if not isinstance(value, str) or not value.strip():
            raise NewsPayloadError(
                f"news provider article is missing required field {field}"
            )
        return value.strip()

    @staticmethod
    def _parse_published_at(value: object) -> datetime:
        if not isinstance(value, str):
            raise NewsPayloadError("news provider returned an invalid publication time")

        try:
            published_at = datetime.fromisoformat(value)
        except ValueError as exc:
            raise NewsPayloadError(
                "news provider returned an invalid publication time"
            ) from exc

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        return published_at.astimezone(UTC)
