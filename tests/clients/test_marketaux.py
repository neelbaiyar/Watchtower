"""Marketaux boundary tests with an in-process HTTP transport."""

import http.server
import json
import logging
import threading
import traceback
from collections.abc import Iterator
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


def build_client(transport: httpx.BaseTransport) -> MarketauxClient:
    # MockTransport intercepts requests in memory, so tests exercise request
    # construction and response parsing without using an API token or network.
    return MarketauxClient(api_token=API_TOKEN, transport=transport)


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

    client = build_client(httpx.MockTransport(handle_request))
    try:
        headlines = client.get_headlines(" aapl ", limit=2)
    finally:
        client.close()

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

    client = build_client(httpx.MockTransport(handle_request))
    try:
        assert client.get_headlines("HPE") == []
    finally:
        client.close()


@pytest.mark.parametrize("status_code", [401, 403])
def test_authentication_errors_are_owned(status_code: int) -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="provider-auth-details")

    client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsAuthenticationError) as error:
            client.get_headlines("HPE")
    finally:
        client.close()

    assert str(error.value) == "news provider rejected credentials"
    assert "provider-auth-details" not in str(error.value)


@pytest.mark.parametrize("status_code", [402, 429])
def test_rate_limit_has_a_distinct_owned_error(status_code: int) -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="provider-rate-limit-details")

    client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsRateLimitError, match="rate limit reached"):
            client.get_headlines("HPE")
    finally:
        client.close()


def test_provider_failure_does_not_leak_body_or_token() -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider-internal-details")

    client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsRequestError) as error:
            client.get_headlines("HPE")
    finally:
        client.close()

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

    client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(NewsPayloadError, match="publication time"):
            client.get_headlines("HPE")
    finally:
        client.close()


@pytest.fixture
def local_news_server() -> Iterator[tuple[str, list[str]]]:
    """Serve one fixed payload on a loopback port and record requested paths."""

    requested_paths: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requested_paths.append(self.path)
            body = json.dumps(NEWS_PAYLOAD).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/news/all", requested_paths
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_token_is_sent_but_never_logged_with_request_logging_enabled(
    local_news_server: tuple[str, list[str]],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A real socket is used so both httpx and the httpcore layer beneath it
    # produce the log lines they would in production.
    news_url, requested_paths = local_news_server
    monkeypatch.setattr(MarketauxClient, "NEWS_URL", news_url)

    with caplog.at_level(logging.DEBUG):
        with MarketauxClient(api_token=API_TOKEN) as client:
            headlines = client.get_headlines("HPE")

    assert len(headlines) == 1
    assert len(requested_paths) == 1
    assert f"api_token={API_TOKEN}" in requested_paths[0]
    # The request line proves request logging was on, so its silence about
    # the token means something.
    assert any(
        record.name == "httpx" and "HTTP Request: GET" in record.getMessage()
        for record in caplog.records
    )
    assert API_TOKEN not in caplog.text
    assert "api_token" not in caplog.text


def test_token_is_absent_from_a_failed_request_and_its_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with caplog.at_level(logging.DEBUG):
        with build_client(httpx.MockTransport(handle_request)) as client:
            with pytest.raises(NewsRequestError) as error:
                client.get_headlines("HPE")

    cause = error.value.__cause__
    assert isinstance(cause, httpx.ConnectError)
    rendered = "".join(traceback.format_exception(error.value))
    assert API_TOKEN not in rendered
    assert API_TOKEN not in caplog.text


def test_status_error_text_does_not_contain_the_token() -> None:
    # httpx puts the request URL in this message, which is the first thing a
    # developer logs when debugging a provider failure.
    seen: list[httpx.Response] = []

    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="provider-internal-details")

    client = build_client(httpx.MockTransport(handle_request))
    client._http.event_hooks["response"].append(seen.append)
    try:
        with pytest.raises(NewsRequestError):
            client.get_headlines("HPE")
    finally:
        client.close()

    (response,) = seen
    assert API_TOKEN not in str(response.request.url)
    with pytest.raises(httpx.HTTPStatusError) as status_error:
        response.raise_for_status()
    assert API_TOKEN not in str(status_error.value)
