from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from watchtower.api.app import create_app
from watchtower.clients.marketaux import NewsRateLimitError
from watchtower.clients.sec_edgar import SecRequestError, SecTickerNotFoundError
from watchtower.schemas import CompanySnapshotResponse


def snapshot_response() -> CompanySnapshotResponse:
    retrieved_at = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)
    return CompanySnapshotResponse.model_validate(
        {
            "ticker": "HPE",
            "company_name": "Hewlett Packard Enterprise Co",
            "cik": "0001645590",
            "generated_at": retrieved_at,
            "filings": {
                "source": {
                    "provider": "SEC EDGAR",
                    "retrieved_at": retrieved_at,
                },
                "items": [],
            },
            "price": {
                "source": {
                    "provider": "Yahoo Finance via yfinance",
                    "retrieved_at": retrieved_at,
                },
                "data": {
                    "price_date": "2026-09-25",
                    "currency": "USD",
                    "latest_close": 63.73,
                    "previous_close": 63.52,
                    "change": 0.21,
                    "change_percent": 0.3306,
                },
            },
            "news": {
                "source": {
                    "provider": "Marketaux",
                    "retrieved_at": retrieved_at,
                },
                "items": [],
            },
        }
    )


class FakeSnapshotService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.requested_tickers: list[str] = []

    def get_company_snapshot(self, ticker: str) -> CompanySnapshotResponse:
        self.requested_tickers.append(ticker)
        if self.error is not None:
            raise self.error
        return snapshot_response()


def test_snapshot_route_returns_owned_response() -> None:
    service = FakeSnapshotService()

    with TestClient(create_app(snapshot_service=service)) as client:
        response = client.get("/companies/HPE/snapshot")

    assert response.status_code == 200
    assert service.requested_tickers == ["HPE"]
    payload = response.json()
    assert payload["ticker"] == "HPE"
    assert payload["price"]["data"]["latest_close"] == 63.73
    assert payload["generated_at"] == "2026-09-25T16:00:00Z"


def test_docs_and_openapi_describe_snapshot_contract() -> None:
    service = FakeSnapshotService()

    with TestClient(create_app(snapshot_service=service)) as client:
        docs_response = client.get("/docs")
        openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert '"docExpansion": "full"' in docs_response.text
    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    assert openapi["tags"] == [
        {
            "name": "Company snapshots",
            "description": (
                "Retrieve one source-grounded research snapshot using a ticker "
                "as input."
            ),
        }
    ]
    operation = openapi["paths"]["/companies/{ticker}/snapshot"]["get"]
    assert operation["summary"] == "Research a company by ticker"
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert response_schema["$ref"].endswith("/CompanySnapshotResponse")


def test_malformed_ticker_is_rejected_before_service_call() -> None:
    service = FakeSnapshotService()

    with TestClient(create_app(snapshot_service=service)) as client:
        response = client.get("/companies/THIS-TICKER-IS-TOO-LONG/snapshot")

    assert response.status_code == 422
    assert service.requested_tickers == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (SecTickerNotFoundError("private details"), 404, "Ticker not found"),
        (
            SecRequestError("private details"),
            502,
            "Upstream provider request failed",
        ),
        (
            NewsRateLimitError("private details"),
            503,
            "News provider temporarily unavailable",
        ),
    ],
)
def test_owned_errors_become_controlled_http_responses(
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    service = FakeSnapshotService(error=error)

    with TestClient(create_app(snapshot_service=service)) as client:
        response = client.get("/companies/HPE/snapshot")

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert "private details" not in response.text
