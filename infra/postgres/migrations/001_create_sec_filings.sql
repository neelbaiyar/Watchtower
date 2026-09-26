-- One accession number identifies one SEC filing. The composite primary key
-- makes repeated polling idempotent for each SEC company identifier.
CREATE TABLE sec_filings (
    cik TEXT NOT NULL CHECK (cik ~ '^[0-9]{10}$'),
    accession_number TEXT NOT NULL,
    form TEXT NOT NULL CHECK (form = '8-K'),
    filing_date DATE NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (cik, accession_number)
);
