"""Contract tests for Watchtower's public JSON schema models."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from watchtower.schemas.company_snapshot import (
    CompanySnapshotResponse,
    DailyPriceResponse,
    SourceMetadata,
)


def valid_snapshot_data() -> dict[str, object]:
    # This is deliberately Watchtower-shaped data, not copied provider JSON. It
    # acts as the shared valid baseline for validation-focused test cases.
    retrieved_at = "2026-09-25T16:00:00Z"
    return {
        "ticker": "HPE",
        "company_name": "Hewlett Packard Enterprise Co",
        "cik": "0001645590",
        "generated_at": retrieved_at,
        "filings": {
            "source": {
                "provider": "SEC EDGAR",
                "retrieved_at": retrieved_at,
            },
            "items": [
                {
                    "accession_number": "0001645590-26-000078",
                    "form": "8-K",
                    "filing_date": "2026-09-02",
                    "report_date": "2026-08-28",
                    "document_url": (
                        "https://www.sec.gov/Archives/edgar/data/1645590/"
                        "000164559026000078/hpe-20260902.htm"
                    ),
                }
            ],
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
            "items": [
                {
                    "title": "HPE reaches a 52-week high",
                    "snippet": "The shares reached a new high.",
                    "url": "https://example.com/hpe-high",
                    "published_at": "2026-09-25T12:15:18Z",
                    "publisher": "Example News",
                }
            ],
        },
    }


def test_company_snapshot_serializes_as_owned_json() -> None:
    snapshot = CompanySnapshotResponse.model_validate(valid_snapshot_data())

    payload = snapshot.model_dump(mode="json")

    assert payload["ticker"] == "HPE"
    assert payload["generated_at"] == "2026-09-25T16:00:00Z"
    assert payload["filings"]["source"]["provider"] == "SEC EDGAR"
    assert payload["filings"]["items"][0]["form"] == "8-K"
    assert payload["price"]["data"]["price_date"] == "2026-09-25"
    assert payload["news"]["items"][0]["publisher"] == "Example News"
    assert payload["news"]["items"][0]["url"] == "https://example.com/hpe-high"


def test_timestamps_must_include_a_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        SourceMetadata(
            provider="SEC EDGAR",
            retrieved_at=datetime(2026, 9, 25, 16, 0),
        )


def test_extra_fields_are_rejected() -> None:
    data = valid_snapshot_data()
    data["recommendation"] = "buy"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CompanySnapshotResponse.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latest_close", 0),
        ("latest_close", float("nan")),
        ("currency", "dollars"),
    ],
)
def test_invalid_price_values_are_rejected(field: str, value: object) -> None:
    price_data = {
        "price_date": date(2026, 9, 25),
        "currency": "USD",
        "latest_close": 63.73,
        "previous_close": 63.52,
        "change": 0.21,
        "change_percent": 0.3306,
        field: value,
    }

    with pytest.raises(ValidationError):
        DailyPriceResponse.model_validate(price_data)


def test_valid_aware_datetime_is_preserved() -> None:
    retrieved_at = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)

    metadata = SourceMetadata(provider="Marketaux", retrieved_at=retrieved_at)

    assert metadata.retrieved_at == retrieved_at
