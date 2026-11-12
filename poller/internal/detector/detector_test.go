// The detector test proves idempotency with a deliberately tiny fake SEC source.
package detector

import (
	"context"
	"testing"
	"time"

	"github.com/neelbaiyar/Watchtower/poller/internal/edgar"
)

func TestPollOnceReportsEachAccessionOnlyOnce(t *testing.T) {
	t.Parallel()

	source := &fakeFilingSource{filings: []edgar.Filing{
		{
			CIK:             "0000320193",
			AccessionNumber: "0000320193-26-000001",
			Form:            "8-K",
			FilingDate:      time.Date(2026, time.September, 25, 0, 0, 0, 0, time.UTC),
		},
	}}
	detector, err := New(source, NewMemorySeenStore(), 5)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}

	// The first observation is new; the exact same accession on the next pass
	// must be ignored even though the source returns it again.
	firstPass, err := detector.PollOnce(context.Background(), "0000320193")
	if err != nil {
		t.Fatalf("first PollOnce() error = %v", err)
	}
	if len(firstPass) != 1 {
		t.Fatalf("first PollOnce() returned %d filings, want 1", len(firstPass))
	}

	secondPass, err := detector.PollOnce(context.Background(), "0000320193")
	if err != nil {
		t.Fatalf("second PollOnce() error = %v", err)
	}
	if len(secondPass) != 0 {
		t.Errorf("second PollOnce() returned %d filings, want 0", len(secondPass))
	}
	if source.calls != 2 {
		t.Errorf("source calls = %d, want 2", source.calls)
	}
	if source.cik != "0000320193" {
		t.Errorf("source CIK = %q, want requested CIK", source.cik)
	}
	if source.limit != 5 {
		t.Errorf("source limit = %d, want detector limit", source.limit)
	}
}

type fakeFilingSource struct {
	// The recorded call values show that Detector forwards its caller's CIK and
	// its configured limit instead of hardcoding either one.
	filings []edgar.Filing
	calls   int
	cik     string
	limit   int
}

func (source *fakeFilingSource) Recent8K(_ context.Context, cik string, limit int) ([]edgar.Filing, error) {
	source.calls++
	source.cik = cik
	source.limit = limit
	return source.filings, nil
}
