CREATE TABLE sec_poll_targets (
    cik TEXT PRIMARY KEY CHECK (cik ~ '^[0-9]{10}$'),
    baselined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE sec_filings
    ADD COLUMN is_baseline BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE sec_refresh_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cik TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cik, accession_number),
    FOREIGN KEY (cik, accession_number)
        REFERENCES sec_filings (cik, accession_number)
);
