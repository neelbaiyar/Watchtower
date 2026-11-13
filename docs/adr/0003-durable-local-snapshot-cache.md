# ADR 0003: Persist complete public snapshots in local PostgreSQL

## Status

Accepted.

## Context

The local dashboard originally made live SEC, price, and news requests for
every selection. That made the experience slow, repeatedly spent the limited
news budget, and could not show prior research when a provider was unavailable
or the application restarted.

The Go poller already uses local PostgreSQL to persist normalized SEC filing
history. Watchtower needs a durable cache that both the Python application and
future refresh work can use without sharing raw vendor payloads.

## Decision

Store a complete, validated `CompanySnapshotResponse` as JSONB in PostgreSQL,
keyed by normalized ticker and paired with `generated_at` and `cached_at`
timestamps.

- A fresh entry is returned as `cached` without making provider calls.
- A browser or API caller can use `refresh=true` to force a live provider
  refresh. A per-ticker cooldown (60 seconds by default) ignores the flag while
  the stored snapshot is younger than that, because the endpoint is
  unauthenticated and each live snapshot spends one request from a small daily
  news quota. The cooldown is read from the stored `cached_at` time rather than
  an in-memory timer, so it survives restarts.
- A provider failure returns the last stored response as `stale` when available.
- A live response remains usable if the optional cache cannot be written.
- The cache is enabled only when `WATCHTOWER_SNAPSHOT_DATABASE_URL` is set.
- The store uses a small connection pool that checks each connection before
  use. A single long-lived connection stayed dead after a PostgreSQL restart,
  which silently disabled the cache until the application restarted. While no
  healthy connection is available, a lookup gives up after two seconds and is
  treated as a cache miss.

The public response declares `snapshot_status` as `live`, `cached`, or
`stale`. A cached response therefore cannot be mistaken for a current live
response.

## Alternatives considered

- **In-memory cache:** simpler, but lost all data on restart and could not
  share state with the poller.
- **Cache raw provider responses:** would couple application behavior to vendor
  schemas and persist more data than Watchtower needs.
- **Always live requests:** preserves freshness but repeats costly work and has
  no fallback during provider failures.

## Consequences

PostgreSQL/Docker becomes an opt-in requirement for durable dashboard behavior.
The live-only API remains available without it. A later refresh worker can
consume the Go poller's SEC refresh requests and replace stale snapshots.
