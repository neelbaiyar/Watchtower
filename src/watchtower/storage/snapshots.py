"""PostgreSQL cache for validated Watchtower snapshot responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from watchtower.schemas import CompanySnapshotResponse


class SnapshotStoreError(RuntimeError):
    """Raised when the optional durable snapshot cache cannot be used."""


@dataclass(frozen=True, slots=True)
class CachedSnapshot:
    """A public snapshot plus the time Watchtower persisted it locally."""

    snapshot: CompanySnapshotResponse
    cached_at: datetime


class SnapshotStore(Protocol):
    """Narrow storage contract used by the application service."""

    def load(self, ticker: str) -> CachedSnapshot | None: ...

    def save(self, snapshot: CompanySnapshotResponse) -> None: ...


class PostgresSnapshotStore:
    """Persist and retrieve complete validated snapshots using PostgreSQL."""

    APPLICATION_NAME = "watchtower-snapshot-cache"
    # A cache lookup must never hold a request for long. When no healthy
    # connection is available within this time the caller gets a cache miss.
    CHECKOUT_TIMEOUT_SECONDS = 2.0

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @classmethod
    def connect(
        cls,
        database_url: str,
        *,
        application_name: str = APPLICATION_NAME,
        startup_timeout_seconds: float = 5.0,
    ) -> PostgresSnapshotStore:
        """Open and validate the optional local cache connection pool."""

        # One long-lived connection dies for good when PostgreSQL restarts. A
        # pool checks each connection as it is handed out, discards dead ones,
        # and keeps reconnecting in the background.
        pool = ConnectionPool(
            database_url,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "application_name": application_name,
            },
            min_size=1,
            max_size=4,
            open=False,
            check=ConnectionPool.check_connection,
            timeout=cls.CHECKOUT_TIMEOUT_SECONDS,
            name=application_name,
        )
        store = cls(pool)
        try:
            pool.open(wait=True, timeout=startup_timeout_seconds)
            store._require_snapshot_table()
        except psycopg.Error as error:
            pool.close()
            raise SnapshotStoreError("connect to snapshot cache") from error
        except SnapshotStoreError:
            pool.close()
            raise
        return store

    def close(self) -> None:
        """Release the database connections held for this application process."""

        self._pool.close()

    def load(self, ticker: str) -> CachedSnapshot | None:
        """Return the last stored snapshot for a normalized ticker, if any."""

        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    """
                    SELECT snapshot, cached_at
                    FROM company_snapshots
                    WHERE ticker = %s
                    """,
                    (ticker,),
                ).fetchone()
        except psycopg.Error as error:
            raise SnapshotStoreError("load cached snapshot") from error

        if row is None:
            return None

        try:
            snapshot = CompanySnapshotResponse.model_validate(row["snapshot"])
            cached_at = _as_utc(row["cached_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise SnapshotStoreError("validate cached snapshot") from error
        return CachedSnapshot(snapshot=snapshot, cached_at=cached_at)

    def save(self, snapshot: CompanySnapshotResponse) -> None:
        """Upsert a live Watchtower response as the current durable snapshot."""

        payload = snapshot.model_dump(mode="json")
        try:
            with self._pool.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO company_snapshots (ticker, snapshot, generated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        snapshot = EXCLUDED.snapshot,
                        generated_at = EXCLUDED.generated_at,
                        cached_at = CURRENT_TIMESTAMP
                    """,
                    (snapshot.ticker, Jsonb(payload), snapshot.generated_at),
                )
        except psycopg.Error as error:
            raise SnapshotStoreError("save cached snapshot") from error

    def _require_snapshot_table(self) -> None:
        """Fail clearly when an existing database has not received migration 003."""

        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT to_regclass('public.company_snapshots') AS table_name"
            ).fetchone()
        if row is None or row["table_name"] is None:
            raise SnapshotStoreError(
                "company_snapshots table is missing; apply PostgreSQL migrations"
            )


def _as_utc(value: object) -> datetime:
    """Normalize the database timestamp before comparing it with the cache TTL."""

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("cached_at must be a timezone-aware datetime")
    return value.astimezone(UTC)
