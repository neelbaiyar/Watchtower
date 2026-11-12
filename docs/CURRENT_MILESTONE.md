# Current Milestone

This file is the scope boundary for active work. Update it when evidence
changes, not whenever a new idea appears.

## Milestone 11: Durable Local Snapshot Cache

**Status:** Complete — ready for review

### Goal

Make Watchtower's complete, normalized company snapshots durable across local
application restarts. A recent stored snapshot should reduce repeated provider
calls, and a prior complete snapshot should remain available when a provider is
temporarily unavailable.

### User and System Value

A browser-local watchlist remembers which tickers matter to the user, but it
does not preserve research data. A durable cache makes the dashboard faster,
protects the limited news request budget, and provides an honest stale fallback
instead of a dead end during a transient provider outage.

### Concepts

- A cache stores reusable results; its time-to-live controls freshness.
- A cache fallback is resilient only when it marks stored data as non-live.
- JSONB stores validated Watchtower-owned JSON without coupling storage to raw
  provider payloads.
- `refresh=true` is an explicit request for a live refresh rather than an
  accidental background call.

### Selected Design

Use the existing local PostgreSQL instance, enabled only by
`WATCHTOWER_SNAPSHOT_DATABASE_URL`. Store a full validated
`CompanySnapshotResponse` per ticker. A fresh entry returns `cached`; a live
provider failure returns the last complete entry as `stale`; a normal success
returns `live` and replaces the cache.

The FastAPI route remains thin. The service owns cache policy and a storage
adapter owns SQL. No raw provider payload, credential, or proprietary logic is
stored.

### Files

- `infra/postgres/migrations/003_create_company_snapshots.sql`
- `src/watchtower/storage/snapshots.py`
- `src/watchtower/services/company_snapshot.py`
- `src/watchtower/api/app.py`
- `src/watchtower/api/routes.py`
- `src/watchtower/schemas/company_snapshot.py`
- `src/watchtower/web/`
- `tests/storage/test_postgres_snapshots.py`
- `tests/services/test_company_snapshot_service.py`
- `docs/adr/0003-durable-local-snapshot-cache.md`
- `README.md`

### Build Order

- [x] Define public `live`, `cached`, and `stale` snapshot status.
- [x] Add a versioned PostgreSQL table for complete owned snapshots.
- [x] Implement cache read, write, freshness, forced refresh, and stale
      fallback behavior behind a narrow storage contract.
- [x] Show status and original generation time in the dashboard.
- [x] Add unit tests for cache policy and an opt-in PostgreSQL round-trip test.
- [x] Restore the last selected browser-local ticker at startup and show its
      explicit snapshot status plus last-refresh time.
- [x] Run complete Python and Go quality checks, manually inspect the local
      dashboard, and perform a staged secret scan.

### Completion Evidence

- Python formatting and lint pass; 52 tests pass and the opt-in PostgreSQL
  integration test passes when run against the local Docker database.
- Go poller tests and static analysis pass.
- The local dashboard was manually inspected for its readable neutral startup
  state; server tests verify delivery of the saved-watchlist startup code.
- The staged public diff passed credential, key-file, and whitespace checks.

### Acceptance Criteria

- [x] A successful complete snapshot is stored under its normalized ticker.
- [x] A fresh entry avoids external provider calls and is labeled `cached`.
- [x] `refresh=true` bypasses a fresh entry and requests current provider data.
- [x] A live provider failure returns the last complete stored response as
      `stale`; an uncached ticker still gets a controlled provider error.
- [x] Stored snapshots survive a Python process boundary in local PostgreSQL.
- [x] The dashboard presents live, cached, and stale status clearly alongside
      the original generation time.
- [x] Tests, formatting, linting, a real local database integration check, and
      a staged secret scan pass.

### Explicitly Out of Scope

- A recurring poller schedule, server-managed watchlist, or refresh-worker
  consumption of SEC outbox requests.
- User accounts, deployment, shared watchlists, or public hosting.
- An LLM, trained prediction model, investment recommendation, or trading
  behavior.
- Any private consequence-engine implementation, model weights, evaluation
  data, or proprietary feature engineering.
