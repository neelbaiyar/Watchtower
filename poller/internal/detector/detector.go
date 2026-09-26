// Package detector decides which SEC filings are newly observed by Watchtower.
package detector

import (
	"context"
	"errors"
	"fmt"

	"github.com/neelbaiyar/Watchtower/poller/internal/edgar"
)

var ErrInvalidConfiguration = errors.New("invalid filing detector configuration")

// FilingSource is the small behavior the detector needs from SEC EDGAR. The
// detector does not need to know URLs, headers, or provider JSON fields.
type FilingSource interface {
	Recent8K(ctx context.Context, cik string, limit int) ([]edgar.Filing, error)
}

// SeenStore atomically records whether Watchtower has already observed an
// accession number. PostgreSQL will later provide durable behavior here.
type SeenStore interface {
	MarkSeen(ctx context.Context, filing edgar.Filing) (isNew bool, err error)
}

// Detector coordinates one retrieval pass and removes filings already seen.
type Detector struct {
	source FilingSource
	seen   SeenStore
	limit  int
}

func New(source FilingSource, seen SeenStore, limit int) (*Detector, error) {
	if source == nil {
		return nil, fmt.Errorf("%w: filing source is required", ErrInvalidConfiguration)
	}
	if seen == nil {
		return nil, fmt.Errorf("%w: seen store is required", ErrInvalidConfiguration)
	}
	if limit < 1 {
		return nil, fmt.Errorf("%w: filing limit must be at least one", ErrInvalidConfiguration)
	}

	return &Detector{source: source, seen: seen, limit: limit}, nil
}

// PollOnce returns only filings that have not appeared in an earlier pass.
func (d *Detector) PollOnce(ctx context.Context, cik string) ([]edgar.Filing, error) {
	filings, err := d.source.Recent8K(ctx, cik, d.limit)
	if err != nil {
		return nil, fmt.Errorf("retrieve filings: %w", err)
	}

	newFilings := make([]edgar.Filing, 0, len(filings))
	for _, filing := range filings {
		isNew, err := d.seen.MarkSeen(ctx, filing)
		if err != nil {
			return nil, fmt.Errorf("record filing %s: %w", filing.AccessionNumber, err)
		}
		if isNew {
			newFilings = append(newFilings, filing)
		}
	}

	return newFilings, nil
}

// MemorySeenStore proves duplicate prevention in this milestone. Its contents
// disappear on process exit, so it is deliberately not production persistence.
type MemorySeenStore struct {
	accessionNumbers map[string]struct{}
}

func NewMemorySeenStore() *MemorySeenStore {
	return &MemorySeenStore{accessionNumbers: make(map[string]struct{})}
}

func (store *MemorySeenStore) MarkSeen(_ context.Context, filing edgar.Filing) (bool, error) {
	if filing.CIK == "" || filing.AccessionNumber == "" {
		return false, errors.New("filing CIK and accession number are required")
	}

	key := filing.CIK + ":" + filing.AccessionNumber
	if _, alreadySeen := store.accessionNumbers[key]; alreadySeen {
		return false, nil
	}

	store.accessionNumbers[key] = struct{}{}
	return true, nil
}
