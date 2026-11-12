// The one-shot runner is tested with in-memory collaborators, never live SEC
// or PostgreSQL services. That keeps orchestration tests quick and repeatable.
package pollrun

import (
	"bytes"
	"context"
	"log"
	"strings"
	"testing"
	"time"

	"github.com/neelbaiyar/Watchtower/poller/internal/edgar"
	"github.com/neelbaiyar/Watchtower/poller/internal/storage"
)

func TestRunOncePollsEachConfiguredCIK(t *testing.T) {
	t.Parallel()

	// Each fake records how it was called so the test verifies collaboration,
	// not just the final no-error result.
	source := &fakeSource{filingsByCIK: map[string][]edgar.Filing{
		"0000320193": {testFiling("0000320193", "0000320193-26-000001")},
		"0000789019": {testFiling("0000789019", "0000789019-26-000001")},
	}}
	recorder := &fakeRecorder{}
	var output bytes.Buffer
	logger := log.New(&output, "", 0)

	err := RunOnce(context.Background(), []string{"0000320193", "0000789019"}, 5, source, recorder, logger)
	if err != nil {
		t.Fatalf("RunOnce() error = %v", err)
	}
	if strings.Join(source.requestedCIKs, ",") != "0000320193,0000789019" {
		t.Errorf("source CIKs = %#v, want each configured CIK", source.requestedCIKs)
	}
	if len(recorder.recordedCIKs) != 2 {
		t.Errorf("recorder calls = %d, want 2", len(recorder.recordedCIKs))
	}
	if count := strings.Count(output.String(), "completed CIK="); count != 2 {
		t.Errorf("completion logs = %d, want 2", count)
	}
}

type fakeSource struct {
	// requestedCIKs is an observation log used by the assertion above.
	filingsByCIK  map[string][]edgar.Filing
	requestedCIKs []string
}

func (source *fakeSource) Recent8K(_ context.Context, cik string, _ int) ([]edgar.Filing, error) {
	source.requestedCIKs = append(source.requestedCIKs, cik)
	return source.filingsByCIK[cik], nil
}

type fakeRecorder struct {
	// This fake does not persist rows; it only captures the runner's intent.
	recordedCIKs []string
}

func (recorder *fakeRecorder) RecordPoll(_ context.Context, cik string, _ []edgar.Filing) (storage.PollResult, error) {
	recorder.recordedCIKs = append(recorder.recordedCIKs, cik)
	return storage.PollResult{IsBaseline: true, NewFilingCount: 1}, nil
}

func testFiling(cik, accessionNumber string) edgar.Filing {
	return edgar.Filing{
		CIK:             cik,
		AccessionNumber: accessionNumber,
		Form:            "8-K",
		FilingDate:      time.Date(2026, time.September, 26, 0, 0, 0, 0, time.UTC),
	}
}
