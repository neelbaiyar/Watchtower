# Current Milestone

This file is the scope boundary for active work. Update it when evidence
changes, not whenever a new idea appears.

## Milestone 8: One-Shot Go Poller Command

**Status:** Complete — ready for review

### Goal

Wire the completed Go SEC client and PostgreSQL recorder into an explicit
one-shot command. Given configured CIKs, it retrieves recent 8-Ks and records
each polling result, then exits.

The command is deliberate: it does not start a recurring loop or make a live
SEC request unless a user runs it with `--once` and real configuration.

### User and System Value

This proves the completed components operate together through a safe, visible
entry point. It creates a runnable baseline before we introduce automated
scheduling or background concurrency.

### Concepts

- Runtime configuration supplies environment-specific values outside source.
- Dependency wiring creates real clients at the application boundary.
- A one-shot command is a bounded operation that completes and exits.
- An orchestration test verifies component collaboration with fakes.

### Architecture Boundary

```text
--once command
    -> configuration: CIKs, SEC identity, database URL
    -> SEC client
    -> PostgreSQL recorder
    -> safe summary log
```

The command owns configuration and real dependency construction. The runner
owns the loop over configured CIKs. Existing SEC and storage packages retain
their provider and SQL responsibilities.

### Selected Design

Use one comma-separated `WATCHTOWER_POLLER_CIKS` environment value and require
the existing SEC User-Agent plus a PostgreSQL URL. This avoids hardcoded
companies and makes a local run reproducible. The default command remains idle;
only `--once` enables polling behavior.

### Files

- `poller/internal/config/config.go`
- `poller/internal/config/config_test.go`
- `poller/internal/pollrun/once.go`
- `poller/internal/pollrun/once_test.go`
- `poller/cmd/poller/main.go`
- `README.md`
- `.env.example`
- `docs/CURRENT_MILESTONE.md`

### Build Order

- [x] Parse and validate runtime configuration without exposing secrets.
- [x] Implement a one-shot runner over configured CIKs.
- [x] Wire `--once` to real SEC and PostgreSQL components.
- [x] Test the runner with fake source and recorder objects.
- [x] Document local setup and the one-shot command.
- [x] Run Go quality checks and existing Python checks.

### Smallest Unfinished Piece

Review the one-shot command and its configuration before adding automated
scheduling in a future milestone.

### Acceptance Criteria

- [x] No ticker or CIK is hardcoded into the command.
- [x] Missing or malformed runtime configuration fails clearly before polling.
- [x] `--once` polls every configured CIK then exits.
- [x] Default startup makes no SEC request.
- [x] Runner tests make no live network or database request.
- [x] README contains local-only setup and run instructions.
- [x] Go and Python quality checks pass.
- [x] No recurring scheduler, retry policy, rate limiter, Python refresh
      worker, cache, ML, or UI behavior changes.

### Explicitly Out of Scope

- Ticker-to-CIK resolution, database-managed watchlists, or a recurring loop.
- Rate limiting, retry/backoff, advisory locks, or concurrent workers.
- Python consumption of refresh requests, cache-backed API reads, ML, scoring,
  and UI work.
