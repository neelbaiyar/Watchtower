"""Opt-in integration tests for the local PostgreSQL snapshot cache."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from watchtower.schemas import CompanySnapshotResponse
from watchtower.storage import PostgresSnapshotStore

TEST_DATABASE_URL_VARIABLE = "WATCHTOWER_TEST_DATABASE_URL"
TEST_TICKER = "WTCACHE"


def _snapshot() -> CompanySnapshotResponse:
    """Build a small valid Watchtower response without provider calls."""

    timestamp = datetime(2026, 11, 12, 16, 0, tzinfo=UTC)
    return CompanySnapshotResponse.model_validate(
        {
            "ticker": TEST_TICKER,
            "company_name": "Watchtower Cache Test",
            "cik": "0000000001",
            "generated_at": timestamp,
            "filings": {
                "source": {"provider": "SEC EDGAR", "retrieved_at": timestamp},
                "items": [],
            },
            "price": {
                "source": {
                    "provider": "Yahoo Finance via yfinance",
                    "retrieved_at": timestamp,
                },
                "data": {
                    "price_date": "2026-11-12",
                    "currency": "USD",
                    "latest_close": 1.0,
                },
            },
            "news": {
                "source": {"provider": "Marketaux", "retrieved_at": timestamp},
                "items": [],
            },
            "research_signal": {
                "level": "quiet",
                "attention_score": 0,
                "explanation": "No weighted activity is present.",
                "evidence": [],
                "limitation": (
                    "Research-priority signal only; not investment advice or a "
                    "price prediction."
                ),
            },
        }
    )


def test_postgres_snapshot_store_round_trips_a_validated_response() -> None:
    """A local opt-in test proves data survives the Python process boundary."""

    database_url = os.getenv(TEST_DATABASE_URL_VARIABLE)
    if not database_url:
        pytest.skip(f"set {TEST_DATABASE_URL_VARIABLE} to run PostgreSQL integration")

    store = PostgresSnapshotStore.connect(database_url)
    try:
        # This fixed test ticker is removed before and after the test, leaving
        # the user's collected research data untouched.
        store._connection.execute(
            "DELETE FROM company_snapshots WHERE ticker = %s", (TEST_TICKER,)
        )
        snapshot = _snapshot()
        store.save(snapshot)
        loaded = store.load(TEST_TICKER)

        assert loaded is not None
        assert loaded.snapshot == snapshot
        assert loaded.cached_at.tzinfo is not None
    finally:
        store._connection.execute(
            "DELETE FROM company_snapshots WHERE ticker = %s", (TEST_TICKER,)
        )
        store.close()
