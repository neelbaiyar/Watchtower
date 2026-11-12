"""PostgreSQL cache for validated Watchtower snapshot responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

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

    def __init__(self, connection: psycopg.Connection[dict[str, object]]) -> None:
        self._connection = connection

    @classmethod
    def connect(cls, database_url: str) -> PostgresSnapshotStore:
        """Open and validate the optional local cache connection."""

        try:
            connection = psycopg.connect(
                database_url,
                autocommit=True,
                row_factory=dict_row,
            )
            store = cls(connection)
            store._require_snapshot_table()
            return store
        except psycopg.Error as error:
            raise SnapshotStoreError("connect to snapshot cache") from error

    def close(self) -> None:
        """Release the database connection held for this application process."""

        self._connection.close()

    def load(self, ticker: str) -> CachedSnapshot | None:
        """Return the last stored snapshot for a normalized ticker, if any."""

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT snapshot, cached_at
                    FROM company_snapshots
                    WHERE ticker = %s
                    """,
                    (ticker,),
                )
                row = cursor.fetchone()
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
            with self._connection.cursor() as cursor:
                cursor.execute(
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

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.company_snapshots') AS table_name"
            )
            row = cursor.fetchone()
        if row is None or row["table_name"] is None:
            raise SnapshotStoreError(
                "company_snapshots table is missing; apply PostgreSQL migrations"
            )


def _as_utc(value: object) -> datetime:
    """Normalize the database timestamp before comparing it with the cache TTL."""

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("cached_at must be a timezone-aware datetime")
    return value.astimezone(UTC)
