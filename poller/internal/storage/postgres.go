// Package storage provides durable implementations of Watchtower storage needs.
package storage

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/neelbaiyar/Watchtower/poller/internal/edgar"
)

var ErrInvalidConfiguration = errors.New("invalid PostgreSQL store configuration")

// PostgresSeenStore persists observed SEC filings and keeps SQL and
// connection-pool details out of the polling code.
type PostgresSeenStore struct {
	pool *pgxpool.Pool
}

// PollResult describes the durable effect of one completed SEC polling pass.
type PollResult struct {
	IsBaseline      bool
	NewFilingCount  int
	RefreshRequests int
}

func Connect(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, fmt.Errorf("%w: database URL is required", ErrInvalidConfiguration)
	}

	// Creating a pool validates connection settings but does not guarantee the
	// database is reachable, so Ping makes startup failure immediate and clear.
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return nil, fmt.Errorf("create PostgreSQL pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping PostgreSQL: %w", err)
	}

	return pool, nil
}

func NewPostgresSeenStore(pool *pgxpool.Pool) (*PostgresSeenStore, error) {
	if pool == nil {
		return nil, fmt.Errorf("%w: connection pool is required", ErrInvalidConfiguration)
	}
	return &PostgresSeenStore{pool: pool}, nil
}

// MarkSeen inserts one filing. PostgreSQL's primary key makes the operation
// idempotent: a duplicate insert changes zero rows and returns false.
func (store *PostgresSeenStore) MarkSeen(ctx context.Context, filing edgar.Filing) (bool, error) {
	// $1 through $4 are database parameters, not string interpolation. This
	// keeps provider values separate from SQL syntax.
	command, err := store.pool.Exec(ctx, `
		INSERT INTO sec_filings (cik, accession_number, form, filing_date)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (cik, accession_number) DO NOTHING
	`, filing.CIK, filing.AccessionNumber, filing.Form, filing.FilingDate)
	if err != nil {
		return false, fmt.Errorf("insert SEC filing: %w", err)
	}

	// ON CONFLICT makes retries safe: one inserted row means new; zero means
	// this filing was already present under the composite primary key.
	return command.RowsAffected() == 1, nil
}

// RecordPoll stores a complete filing list atomically. The first successful
// poll for a CIK establishes history; only later unseen filings create refresh
// requests for a future Python worker.
func (store *PostgresSeenStore) RecordPoll(ctx context.Context, cik string, filings []edgar.Filing) (PollResult, error) {
	tx, err := store.pool.Begin(ctx)
	if err != nil {
		return PollResult{}, fmt.Errorf("begin filing transaction: %w", err)
	}
	// Rollback is safe even after Commit and protects every early return below
	// from leaving the database in a partial state.
	defer tx.Rollback(ctx)

	target, err := tx.Exec(ctx, `
		INSERT INTO sec_poll_targets (cik)
		VALUES ($1)
		ON CONFLICT (cik) DO NOTHING
	`, cik)
	if err != nil {
		return PollResult{}, fmt.Errorf("record poll target: %w", err)
	}

	// The first inserted poll target establishes history only. We do not create
	// refresh requests for old filings discovered during that initial baseline.
	result := PollResult{IsBaseline: target.RowsAffected() == 1}
	for _, filing := range filings {
		if filing.CIK != cik {
			return PollResult{}, fmt.Errorf("filing CIK %q does not match poll CIK %q", filing.CIK, cik)
		}

		inserted, err := tx.Exec(ctx, `
			INSERT INTO sec_filings (cik, accession_number, form, filing_date, is_baseline)
			VALUES ($1, $2, $3, $4, $5)
			ON CONFLICT (cik, accession_number) DO NOTHING
		`, filing.CIK, filing.AccessionNumber, filing.Form, filing.FilingDate, result.IsBaseline)
		if err != nil {
			return PollResult{}, fmt.Errorf("insert SEC filing: %w", err)
		}
		// Duplicate filings are expected on every later SEC response and require
		// neither another refresh request nor an error.
		if inserted.RowsAffected() == 0 {
			continue
		}

		result.NewFilingCount++
		if result.IsBaseline {
			continue
		}

		refresh, err := tx.Exec(ctx, `
			INSERT INTO sec_refresh_requests (cik, accession_number)
			VALUES ($1, $2)
			ON CONFLICT (cik, accession_number) DO NOTHING
		`, filing.CIK, filing.AccessionNumber)
		if err != nil {
			return PollResult{}, fmt.Errorf("create refresh request: %w", err)
		}
		result.RefreshRequests += int(refresh.RowsAffected())
	}

	// Commit publishes the filing rows and their refresh requests together.
	// Until this succeeds, other consumers cannot observe a half-complete poll.
	if err := tx.Commit(ctx); err != nil {
		return PollResult{}, fmt.Errorf("commit filing transaction: %w", err)
	}
	return result, nil
}
