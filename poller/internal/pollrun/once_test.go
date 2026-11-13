// The one-shot runner is tested with in-memory collaborators, never live SEC
// or PostgreSQL services. That keeps orchestration tests quick and repeatable.
package pollrun

import (
	"bytes"
	"context"
	"errors"
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

func TestRunOnceContinuesPastAFailingCIK(t *testing.T) {
	t.Parallel()

	source := &fakeSource{
		filingsByCIK: map[string][]edgar.Filing{
			"0000789019": {testFiling("0000789019", "0000789019-26-000001")},
		},
		failingCIKs: map[string]error{"0000320193": edgar.ErrRequestFailed},
	}
	recorder := &fakeRecorder{}
	var output bytes.Buffer

	err := RunOnce(context.Background(), []string{"0000320193", "0000789019"}, 5, source, recorder, log.New(&output, "", 0))

	if !errors.Is(err, edgar.ErrRequestFailed) {
		t.Fatalf("RunOnce() error = %v, want the failing CIK's error", err)
	}
	if strings.Join(recorder.recordedCIKs, ",") != "0000789019" {
		t.Errorf("recorded CIKs = %#v, want only the healthy CIK", recorder.recordedCIKs)
	}
	if !strings.Contains(output.String(), "failed CIK=0000320193") {
		t.Errorf("log output = %q, want the failing CIK named", output.String())
	}
}

func TestRunOnceStopsWhenContextIsCancelled(t *testing.T) {
	t.Parallel()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	source := &fakeSource{}
	var output bytes.Buffer

	err := RunOnce(ctx, []string{"0000320193", "0000789019"}, 5, source, &fakeRecorder{}, log.New(&output, "", 0))

	if !errors.Is(err, context.Canceled) {
		t.Fatalf("RunOnce() error = %v, want context.Canceled", err)
	}
	if len(source.requestedCIKs) != 0 {
		t.Errorf("source CIKs = %#v, want no requests after cancellation", source.requestedCIKs)
	}
}

type fakeSource struct {
	// requestedCIKs is an observation log used by the assertions above.
	filingsByCIK  map[string][]edgar.Filing
	failingCIKs   map[string]error
	requestedCIKs []string
}

func (source *fakeSource) Recent8K(_ context.Context, cik string, _ int) ([]edgar.Filing, error) {
	source.requestedCIKs = append(source.requestedCIKs, cik)
	if err := source.failingCIKs[cik]; err != nil {
		return nil, err
	}
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
