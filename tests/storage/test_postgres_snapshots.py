"""Opt-in integration tests for the local PostgreSQL snapshot cache."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest

from watchtower.schemas import CompanySnapshotResponse
from watchtower.storage import PostgresSnapshotStore, SnapshotStoreError

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


@pytest.fixture
def database_url() -> str:
    url = os.getenv(TEST_DATABASE_URL_VARIABLE)
    if not url:
        pytest.skip(f"set {TEST_DATABASE_URL_VARIABLE} to run PostgreSQL integration")
    return url


@pytest.fixture
def application_name() -> str:
    # A unique name lets a test find and drop only its own connections, so a
    # dashboard running against the same local database is left alone.
    return f"watchtower-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def store(database_url: str, application_name: str) -> Iterator[PostgresSnapshotStore]:
    """Yield a store whose fixed test ticker is removed before and after use."""

    snapshot_store = PostgresSnapshotStore.connect(
        database_url,
        application_name=application_name,
    )
    _delete_test_ticker(database_url)
    try:
        yield snapshot_store
    finally:
        snapshot_store.close()
        _delete_test_ticker(database_url)


def _delete_test_ticker(database_url: str) -> None:
    # Only this ticker is touched, leaving collected research data in place.
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            "DELETE FROM company_snapshots WHERE ticker = %s", (TEST_TICKER,)
        )


def _backend_pids(database_url: str, application_name: str) -> set[int]:
    with psycopg.connect(database_url, autocommit=True) as connection:
        rows = connection.execute(
            "SELECT pid FROM pg_stat_activity WHERE application_name = %s",
            (application_name,),
        ).fetchall()
    return {row[0] for row in rows}


def test_postgres_snapshot_store_round_trips_a_validated_response(
    store: PostgresSnapshotStore,
) -> None:
    """A local opt-in test proves data survives the Python process boundary."""

    snapshot = _snapshot()
    store.save(snapshot)
    loaded = store.load(TEST_TICKER)

    assert loaded is not None
    assert loaded.snapshot == snapshot
    assert loaded.cached_at.tzinfo is not None


def test_store_recovers_after_postgres_drops_its_connections(
    store: PostgresSnapshotStore,
    database_url: str,
    application_name: str,
) -> None:
    """Dropping every server-side connection is what a restart looks like."""

    snapshot = _snapshot()
    store.save(snapshot)
    pids_before = _backend_pids(database_url, application_name)
    assert pids_before

    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE application_name = %s
            """,
            (application_name,),
        )

    loaded = store.load(TEST_TICKER)
    store.save(snapshot)

    assert loaded is not None
    assert loaded.snapshot == snapshot
    pids_after = _backend_pids(database_url, application_name)
    assert pids_after
    assert pids_after.isdisjoint(pids_before)


def test_unreachable_database_fails_startup_with_an_owned_error() -> None:
    # Port 1 is reserved and closed, so this needs no running database.
    with pytest.raises(SnapshotStoreError, match="connect to snapshot cache"):
        PostgresSnapshotStore.connect(
            "postgres://watchtower@127.0.0.1:1/watchtower?connect_timeout=1",
            startup_timeout_seconds=0.5,
        )
