# Current Milestone

This file is the scope boundary for active work. Update it when evidence
changes, not whenever a new idea appears.

## Milestone 7: Filing Baseline and Refresh Outbox

**Status:** Complete — verified stopping point

### Goal

Record a CIK's first observed 8-Ks as a baseline with no refresh work. On a
later polling pass, persist each unseen filing and create exactly one durable
refresh request for it in the same PostgreSQL transaction.

### User and System Value

An initial SEC response contains past filings, not necessarily new events. A
baseline prevents Watchtower from spending scarce news calls on old history.
The refresh outbox is durable evidence that a future Python refresh worker has
work to do.

### Concepts

- A transaction makes a related group of database changes succeed or fail as
  one unit.
- A baseline establishes the initial known state without emitting alerts.
- An outbox is a database table recording work for another component to do.
- `ON CONFLICT DO NOTHING` makes a retried insert safe.

### Architecture Boundary

```text
SEC filings
    -> Go recorder transaction
        -> sec_filings
        -> sec_refresh_requests (later new filings only)
```

The recorder owns persistence and refresh-request creation. A future Python
worker will consume the outbox; this milestone does not implement that worker.

### Files

- `infra/postgres/migrations/002_poll_targets_and_refresh_requests.sql`
- `poller/internal/storage/postgres.go`
- `poller/internal/storage/postgres_test.go`
- `docs/CURRENT_MILESTONE.md`

### Build Order

- [x] Add a versioned schema change for poll targets, baseline markers, and
      refresh requests.
- [x] Record a first poll as a baseline inside one transaction.
- [x] Record later unseen filings and one refresh request each.
- [x] Prove duplicate later filings create no extra refresh request.
- [x] Run the local PostgreSQL integration test and Go quality checks.

### Smallest Unfinished Piece

Stop here: baseline and refresh-outbox persistence are complete and verified.

### Acceptance Criteria

- [x] The first poll for a CIK is marked baseline and emits zero refresh work.
- [x] A later new filing inserts one filing and one refresh request.
- [x] Repeating that filing creates neither a duplicate filing nor request.
- [x] Filing plus refresh request are recorded atomically.
- [x] Tests use only the local PostgreSQL container, not live SEC.
- [x] `go test ./...` and `go vet ./...` pass.
- [x] No Python, FastAPI, news/price, cache, ML, or UI behavior changes.

### Explicitly Out of Scope

- Ticker resolution, watched-target loading, scheduling, rate limiting,
  retries, advisory locks, or a recurring loop.
- A Python worker consuming refresh requests.
- Cached FastAPI reads, news/price refreshes, ML, scoring, or UI work.
