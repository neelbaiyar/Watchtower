// Package pollrun coordinates bounded polling operations.
package pollrun

import (
	"context"
	"errors"
	"fmt"
	"log"

	"github.com/neelbaiyar/Watchtower/poller/internal/edgar"
	"github.com/neelbaiyar/Watchtower/poller/internal/storage"
)

var ErrInvalidConfiguration = errors.New("invalid one-shot poller configuration")

type FilingSource interface {
	// The runner needs only this behavior, so a real SEC client and a fake test
	// source can satisfy the same contract.
	Recent8K(ctx context.Context, cik string, limit int) ([]edgar.Filing, error)
}

type PollRecorder interface {
	// Recording is separate from retrieval: this interface owns durable state
	// while the source interface owns provider communication.
	RecordPoll(ctx context.Context, cik string, filings []edgar.Filing) (storage.PollResult, error)
}

// RunOnce polls each configured CIK exactly once, persists its result, then
// returns. It has no timer and never starts background work by itself.
//
// A failure for one CIK does not stop the others: a single delisted or
// misconfigured company would otherwise block every CIK listed after it on
// every run. The returned error joins all per-CIK failures.
func RunOnce(
	ctx context.Context,
	ciks []string,
	filingLimit int,
	source FilingSource,
	recorder PollRecorder,
	logger *log.Logger,
) error {
	if len(ciks) == 0 || filingLimit < 1 || source == nil || recorder == nil || logger == nil {
		return ErrInvalidConfiguration
	}

	// This first command is intentionally sequential. Scheduling, concurrency,
	// and rate limiting require their own milestone and explicit safety rules.
	var failures []error
	for _, cik := range ciks {
		// Cancellation is not a per-CIK problem; stop instead of failing the
		// remaining companies one by one.
		if err := ctx.Err(); err != nil {
			failures = append(failures, err)
			break
		}

		result, err := pollOne(ctx, cik, filingLimit, source, recorder)
		if err != nil {
			logger.Printf("failed CIK=%s", cik)
			failures = append(failures, err)
			continue
		}

		// Log counts and identifiers, not provider JSON or credentials. These
		// messages are useful when running locally without exposing secrets.
		logger.Printf(
			"completed CIK=%s baseline=%t new_filings=%d refresh_requests=%d",
			cik,
			result.IsBaseline,
			result.NewFilingCount,
			result.RefreshRequests,
		)
	}

	return errors.Join(failures...)
}

func pollOne(
	ctx context.Context,
	cik string,
	filingLimit int,
	source FilingSource,
	recorder PollRecorder,
) (storage.PollResult, error) {
	filings, err := source.Recent8K(ctx, cik, filingLimit)
	if err != nil {
		return storage.PollResult{}, fmt.Errorf("retrieve SEC filings for %s: %w", cik, err)
	}
	result, err := recorder.RecordPoll(ctx, cik, filings)
	if err != nil {
		return storage.PollResult{}, fmt.Errorf("record SEC filings for %s: %w", cik, err)
	}
	return result, nil
}
