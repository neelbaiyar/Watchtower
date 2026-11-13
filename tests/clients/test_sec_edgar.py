"""SEC client tests that simulate provider JSON with a local HTTP transport."""

from datetime import date

import httpx
import pytest

from watchtower.clients.sec_edgar import (
    SecEdgarClient,
    SecPayloadError,
    SecRequestError,
    SecTickerNotFoundError,
)

TICKER_PAYLOAD = {
    "0": {
        "cik_str": 1645590,
        "ticker": "HPE",
        "title": "Hewlett Packard Enterprise Co",
    },
    "1": {
        "cik_str": 320193,
        "ticker": "AAPL",
        "title": "Apple Inc.",
    },
}

SUBMISSIONS_PAYLOAD = {
    "filings": {
        "recent": {
            "accessionNumber": [
                "0001645590-26-000111",
                "0001645590-26-000110",
                "0001645590-26-000109",
            ],
            "filingDate": ["2026-09-20", "2026-09-19", "2026-09-18"],
            "reportDate": ["2026-09-20", "2026-07-31", ""],
            "form": ["8-K", "10-Q", "8-K"],
            "primaryDocument": ["hpe-8k.htm", "hpe-10q.htm", "hpe-8k-2.htm"],
        }
    }
}


def build_client(
    handler: httpx.MockTransport,
) -> tuple[SecEdgarClient, httpx.Client]:
    # A mock HTTP client makes the fixture deterministic and prevents tests
    # from hitting the real SEC service or its rate limit.
    http_client = httpx.Client(transport=handler)
    client = SecEdgarClient(
        user_agent="Watchtower tests test@example.com",
        http_client=http_client,
    )
    return client, http_client


def test_recent_8k_filings_are_normalized_and_limited() -> None:
    requested_urls: list[str] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        assert request.headers["User-Agent"] == "Watchtower tests test@example.com"
        if str(request.url) == SecEdgarClient.TICKER_MAPPING_URL:
            return httpx.Response(200, json=TICKER_PAYLOAD)
        if str(request.url).endswith("/CIK0001645590.json"):
            return httpx.Response(200, json=SUBMISSIONS_PAYLOAD)
        return httpx.Response(404)

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        filings = client.get_recent_8k_filings(" hpe ", limit=1)
    finally:
        http_client.close()

    assert len(filings) == 1
    filing = filings[0]
    assert filing.ticker == "HPE"
    assert filing.cik == "0001645590"
    assert filing.company_name == "Hewlett Packard Enterprise Co"
    assert filing.form == "8-K"
    assert filing.filing_date == date(2026, 9, 20)
    assert filing.report_date == date(2026, 9, 20)
    assert filing.primary_document_url == (
        "https://www.sec.gov/Archives/edgar/data/1645590/000164559026000111/hpe-8k.htm"
    )
    assert requested_urls == [
        SecEdgarClient.TICKER_MAPPING_URL,
        "https://data.sec.gov/submissions/CIK0001645590.json",
    ]


def test_ticker_mapping_is_cached_for_multiple_lookups() -> None:
    mapping_requests = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal mapping_requests
        if str(request.url) == SecEdgarClient.TICKER_MAPPING_URL:
            mapping_requests += 1
            return httpx.Response(200, json=TICKER_PAYLOAD)
        return httpx.Response(404)

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        assert client.resolve_company("HPE").cik == "0001645590"
        assert client.resolve_company("aapl").cik == "0000320193"
    finally:
        http_client.close()

    # A process-local mapping cache avoids paying for the large SEC mapping on
    # every ticker lookup while still normalizing separate company records.
    assert mapping_requests == 1


def test_unknown_ticker_raises_owned_error() -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=TICKER_PAYLOAD)

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(SecTickerNotFoundError, match="UNKNOWN"):
            client.resolve_company("unknown")
    finally:
        http_client.close()


def test_inconsistent_recent_arrays_raise_payload_error() -> None:
    malformed_payload = {
        "filings": {
            "recent": {
                **SUBMISSIONS_PAYLOAD["filings"]["recent"],
                "filingDate": ["2026-09-20"],
            }
        }
    }

    def handle_request(request: httpx.Request) -> httpx.Response:
        if str(request.url) == SecEdgarClient.TICKER_MAPPING_URL:
            return httpx.Response(200, json=TICKER_PAYLOAD)
        return httpx.Response(200, json=malformed_payload)

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(SecPayloadError, match="inconsistent lengths"):
            client.get_recent_8k_filings("HPE")
    finally:
        http_client.close()


def test_provider_failure_does_not_leak_response_body() -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider-internal-details")

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(SecRequestError) as error:
            client.resolve_company("HPE")
    finally:
        http_client.close()

    assert str(error.value) == "SEC request failed"
    assert "provider-internal-details" not in str(error.value)


class FakeMonotonic:
    """A clock the test moves by hand, in seconds."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_ticker_mapping_is_downloaded_again_after_its_ttl() -> None:
    mapping_payloads = [
        TICKER_PAYLOAD,
        {
            **TICKER_PAYLOAD,
            "2": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        },
    ]
    mapping_requests = 0

    def handle_request(_: httpx.Request) -> httpx.Response:
        nonlocal mapping_requests
        payload = mapping_payloads[min(mapping_requests, 1)]
        mapping_requests += 1
        return httpx.Response(200, json=payload)

    clock = FakeMonotonic()
    http_client = httpx.Client(transport=httpx.MockTransport(handle_request))
    client = SecEdgarClient(
        user_agent="Watchtower tests test@example.com",
        http_client=http_client,
        monotonic=clock,
    )
    try:
        with pytest.raises(SecTickerNotFoundError):
            client.resolve_company("NVDA")

        # Just inside the default 24 hours the stored mapping is still used.
        clock.now += 24 * 60 * 60 - 1
        with pytest.raises(SecTickerNotFoundError):
            client.resolve_company("NVDA")
        assert mapping_requests == 1

        clock.now += 1
        assert client.resolve_company("NVDA").cik == "0001045810"
        assert mapping_requests == 2
    finally:
        http_client.close()


def test_failed_mapping_refresh_keeps_the_previous_mapping(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mapping_requests = 0

    def handle_request(_: httpx.Request) -> httpx.Response:
        nonlocal mapping_requests
        mapping_requests += 1
        if mapping_requests == 1:
            return httpx.Response(200, json=TICKER_PAYLOAD)
        return httpx.Response(503, text="provider-internal-details")

    clock = FakeMonotonic()
    http_client = httpx.Client(transport=httpx.MockTransport(handle_request))
    client = SecEdgarClient(
        user_agent="Watchtower tests test@example.com",
        http_client=http_client,
        ticker_mapping_ttl_seconds=60,
        monotonic=clock,
    )
    try:
        assert client.resolve_company("HPE").cik == "0001645590"

        clock.now += 61
        with caplog.at_level("WARNING", logger="watchtower.clients.sec_edgar"):
            assert client.resolve_company("HPE").cik == "0001645590"
        assert mapping_requests == 2
        assert "keeping the previous mapping" in caplog.text
        assert "provider-internal-details" not in caplog.text

        # The outage is not retried on every lookup, only after the delay.
        assert client.resolve_company("AAPL").cik == "0000320193"
        assert mapping_requests == 2
        clock.now += SecEdgarClient.TICKER_MAPPING_RETRY_SECONDS
        client.resolve_company("HPE")
        assert mapping_requests == 3
    finally:
        http_client.close()


def test_first_mapping_download_failure_is_still_raised() -> None:
    def handle_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client, http_client = build_client(httpx.MockTransport(handle_request))
    try:
        with pytest.raises(SecRequestError):
            client.resolve_company("HPE")
    finally:
        http_client.close()
