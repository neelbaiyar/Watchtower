-- A poll target records that we have established initial history for one CIK.
-- That lets the application distinguish old baseline filings from new events.
CREATE TABLE sec_poll_targets (
    cik TEXT PRIMARY KEY CHECK (cik ~ '^[0-9]{10}$'),
    baselined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Baseline rows are stored for provenance but deliberately do not create work
-- for the future price/news refresh worker.
ALTER TABLE sec_filings
    ADD COLUMN is_baseline BOOLEAN NOT NULL DEFAULT FALSE;

-- This outbox-style table is the handoff from SEC ingestion to future Python
-- refresh work. Its unique key prevents duplicate downstream work on retries.
CREATE TABLE sec_refresh_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cik TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cik, accession_number),
    FOREIGN KEY (cik, accession_number)
        REFERENCES sec_filings (cik, accession_number)
);
