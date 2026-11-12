-- A complete Watchtower-owned response is stored as validated JSONB. We do
-- not persist raw provider payloads, credentials, or private client details.
CREATE TABLE company_snapshots (
    ticker TEXT PRIMARY KEY CHECK (ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'),
    snapshot JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    cached_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX company_snapshots_cached_at_idx ON company_snapshots (cached_at);
