package storage

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/neelbaiyar/Watchtower/poller/internal/edgar"
)

const testDatabaseURLVariable = "WATCHTOWER_TEST_DATABASE_URL"

func TestPostgresSeenStoreMarksFilingOnlyOnce(t *testing.T) {
	databaseURL := os.Getenv(testDatabaseURLVariable)
	if databaseURL == "" {
		t.Skipf("set %s to run the PostgreSQL integration test", testDatabaseURLVariable)
	}

	ctx := context.Background()
	pool, err := Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Connect() error = %v", err)
	}
	t.Cleanup(pool.Close)

	filing := edgar.Filing{
		CIK:             "0000320193",
		AccessionNumber: "0000320193-26-999999",
		Form:            "8-K",
		FilingDate:      time.Date(2026, time.September, 26, 0, 0, 0, 0, time.UTC),
	}
	if _, err := pool.Exec(ctx,
		"DELETE FROM sec_filings WHERE cik = $1 AND accession_number = $2",
		filing.CIK,
		filing.AccessionNumber,
	); err != nil {
		t.Fatalf("clear test filing: %v", err)
	}

	store, err := NewPostgresSeenStore(pool)
	if err != nil {
		t.Fatalf("NewPostgresSeenStore() error = %v", err)
	}

	firstMark, err := store.MarkSeen(ctx, filing)
	if err != nil {
		t.Fatalf("first MarkSeen() error = %v", err)
	}
	if !firstMark {
		t.Error("first MarkSeen() = false, want true")
	}

	secondMark, err := store.MarkSeen(ctx, filing)
	if err != nil {
		t.Fatalf("second MarkSeen() error = %v", err)
	}
	if secondMark {
		t.Error("second MarkSeen() = true, want false")
	}
}

func TestRecordPollBaselinesThenCreatesOneRefreshRequest(t *testing.T) {
	databaseURL := os.Getenv(testDatabaseURLVariable)
	if databaseURL == "" {
		t.Skipf("set %s to run the PostgreSQL integration test", testDatabaseURLVariable)
	}

	ctx := context.Background()
	pool, err := Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Connect() error = %v", err)
	}
	t.Cleanup(pool.Close)

	cik := "0000320193"
	if _, err := pool.Exec(ctx, "DELETE FROM sec_refresh_requests WHERE cik = $1", cik); err != nil {
		t.Fatalf("clear refresh requests: %v", err)
	}
	if _, err := pool.Exec(ctx, "DELETE FROM sec_filings WHERE cik = $1", cik); err != nil {
		t.Fatalf("clear filings: %v", err)
	}
	if _, err := pool.Exec(ctx, "DELETE FROM sec_poll_targets WHERE cik = $1", cik); err != nil {
		t.Fatalf("clear poll target: %v", err)
	}

	store, err := NewPostgresSeenStore(pool)
	if err != nil {
		t.Fatalf("NewPostgresSeenStore() error = %v", err)
	}

	baselineFiling := testFiling(cik, "0000320193-26-000001")
	baseline, err := store.RecordPoll(ctx, cik, []edgar.Filing{baselineFiling})
	if err != nil {
		t.Fatalf("baseline RecordPoll() error = %v", err)
	}
	if !baseline.IsBaseline || baseline.NewFilingCount != 1 || baseline.RefreshRequests != 0 {
		t.Errorf("baseline result = %#v, want baseline with one filing and zero refreshes", baseline)
	}

	newFiling := testFiling(cik, "0000320193-26-000002")
	later, err := store.RecordPoll(ctx, cik, []edgar.Filing{baselineFiling, newFiling})
	if err != nil {
		t.Fatalf("later RecordPoll() error = %v", err)
	}
	if later.IsBaseline || later.NewFilingCount != 1 || later.RefreshRequests != 1 {
		t.Errorf("later result = %#v, want one new filing and one refresh", later)
	}

	retry, err := store.RecordPoll(ctx, cik, []edgar.Filing{baselineFiling, newFiling})
	if err != nil {
		t.Fatalf("retry RecordPoll() error = %v", err)
	}
	if retry.NewFilingCount != 0 || retry.RefreshRequests != 0 {
		t.Errorf("retry result = %#v, want no duplicate work", retry)
	}
}

func TestRecordPollRollsBackWhenOneFilingHasTheWrongCIK(t *testing.T) {
	databaseURL := os.Getenv(testDatabaseURLVariable)
	if databaseURL == "" {
		t.Skipf("set %s to run the PostgreSQL integration test", testDatabaseURLVariable)
	}

	ctx := context.Background()
	pool, err := Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Connect() error = %v", err)
	}
	t.Cleanup(pool.Close)

	cik := "0000789019"
	if _, err := pool.Exec(ctx, "DELETE FROM sec_refresh_requests WHERE cik = $1", cik); err != nil {
		t.Fatalf("clear refresh requests: %v", err)
	}
	if _, err := pool.Exec(ctx, "DELETE FROM sec_filings WHERE cik = $1", cik); err != nil {
		t.Fatalf("clear filings: %v", err)
	}
	if _, err := pool.Exec(ctx, "DELETE FROM sec_poll_targets WHERE cik = $1", cik); err != nil {
		t.Fatalf("clear poll target: %v", err)
	}

	store, err := NewPostgresSeenStore(pool)
	if err != nil {
		t.Fatalf("NewPostgresSeenStore() error = %v", err)
	}

	_, err = store.RecordPoll(ctx, cik, []edgar.Filing{
		testFiling(cik, "0000789019-26-000001"),
		testFiling("0000320193", "0000320193-26-000003"),
	})
	if err == nil {
		t.Fatal("RecordPoll() error = nil, want mismatched CIK error")
	}

	var targetCount int
	if err := pool.QueryRow(ctx, "SELECT COUNT(*) FROM sec_poll_targets WHERE cik = $1", cik).Scan(&targetCount); err != nil {
		t.Fatalf("count poll targets: %v", err)
	}
	if targetCount != 0 {
		t.Errorf("poll target count = %d, want 0 after rollback", targetCount)
	}

	var filingCount int
	if err := pool.QueryRow(ctx, "SELECT COUNT(*) FROM sec_filings WHERE cik = $1", cik).Scan(&filingCount); err != nil {
		t.Fatalf("count filings: %v", err)
	}
	if filingCount != 0 {
		t.Errorf("filing count = %d, want 0 after rollback", filingCount)
	}

}

func testFiling(cik, accessionNumber string) edgar.Filing {
	return edgar.Filing{
		CIK:             cik,
		AccessionNumber: accessionNumber,
		Form:            "8-K",
		FilingDate:      time.Date(2026, time.September, 26, 0, 0, 0, 0, time.UTC),
	}
}
