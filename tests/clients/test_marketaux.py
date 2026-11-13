"""Marketaux boundary tests with an in-process HTTP transport."""

from datetime import UTC, datetime

import httpx
import pytest

from watchtower.clients.marketaux import (
    MarketauxClient,
    NewsAuthenticationError,
    NewsPayloadError,
    NewsRateLimitError,
    NewsRequestError,
)

API_TOKEN = "test-token"

NEWS_PAYLOAD = {
    "meta": {"found": 1, "returned": 1, "limit": 3, "page": 1},
    "data": [
        {
            "title": "Apple announces a new product",
            "snippet": "The company introduced its latest product.",
            "url": "https://example.com/apple-product",
            "published_at": "2026-09-25T15:30:00Z",
            "source": "Example News",
        }
    ],
}


def build_client(
    transport: httpx.MockTransport,
) -> tuple[MarketauxClient, httpx.Client]:
    # MockTransport intercepts requests in memory, so tests exercise request
    # construction and response parsing without using an API token or network.
    http_client = httpx.Client(transport=transport)
    client = MarketauxClient(api_token=API_TOKEN, http_client=http_client)
    return client, http_client


def test_headlines_are_requested_and_normalized() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        assert str(request.url.copy_with(query=None)) == MarketauxClient.NEWS_URL
        assert request.url.params["api_token"] == API_TOKEN
        assert request.url.params["symbols"] == "AAPL"
        assert request.url.params["filter_entities"] == "true"
        assert request.url.params["language"] == "en"
        assert request.url.params["limit"] == "2"
        # This is provider-shaped input; later assertions inspect only the
        # Watchtower-owned NewsHeadline that the client returns.
        return httpx.Response(200, json=NEWS_PAYLOAD)

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        headlines = client.get_headlines(" aapl ", limit=2)
    finally:
        http_client.close()

    assert len(headlines) == 1
    headline = headlines[0]
    assert headline.ticker == "AAPL"
    assert headline.title == "Apple announces a new product"
    assert headline.snippet == "The company introduced its latest product."
    assert headline.url == "https://example.com/apple-product"
    assert headline.published_at == datetime(2026, 9, 25, 15, 30, tzinfo=UTC)
    assert headline.source == "Example News"


def test_empty_news_result_is_valid() -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {}, "data": []})

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        assert client.get_headlines("HPE") == []
    finally:
        http_client.close()


@pytest.mark.parametrize("status_code", [401, 403])
def test_authentication_errors_are_owned(status_code: int) -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="provider-auth-details")

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsAuthenticationError) as error:
            client.get_headlines("HPE")
    finally:
        http_client.close()

    assert str(error.value) == "news provider rejected credentials"
    assert "provider-auth-details" not in str(error.value)


@pytest.mark.parametrize("status_code", [402, 429])
def test_rate_limit_has_a_distinct_owned_error(status_code: int) -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="provider-rate-limit-details")

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsRateLimitError, match="rate limit reached"):
            client.get_headlines("HPE")
    finally:
        http_client.close()


def test_provider_failure_does_not_leak_body_or_token() -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider-internal-details")

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsRequestError) as error:
            client.get_headlines("HPE")
    finally:
        http_client.close()

    message = str(error.value)
    assert message == "news provider request failed"
    assert "provider-internal-details" not in message
    assert API_TOKEN not in message


def test_malformed_article_raises_owned_payload_error() -> None:
    malformed_payload = {
        "meta": {},
        "data": [{**NEWS_PAYLOAD["data"][0], "published_at": "not-a-date"}],
    }

    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=malformed_payload)

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsPayloadError, match="publication time"):
            client.get_headlines("HPE")
    finally:
        http_client.close()
