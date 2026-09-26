// Package edgar contains Watchtower's boundary to SEC EDGAR submissions data.
package edgar

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const DefaultBaseURL = "https://data.sec.gov"

var (
	ErrInvalidConfiguration = errors.New("invalid SEC client configuration")
	ErrInvalidCIK           = errors.New("invalid SEC CIK")
	ErrInvalidLimit         = errors.New("invalid SEC filing limit")
	ErrRequestFailed        = errors.New("SEC request failed")
	ErrInvalidPayload       = errors.New("invalid SEC submissions payload")
)

// Filing is Watchtower's normalized record for the metadata needed to detect a
// newly filed 8-K. SEC's response structure remains private to this package.
type Filing struct {
	CIK             string
	AccessionNumber string
	Form            string
	FilingDate      time.Time
}

// Client retrieves SEC submissions data with a configured identification
// header. The injected HTTP client makes the provider boundary testable.
type Client struct {
	baseURL    string
	userAgent  string
	httpClient *http.Client
}

// NewClient creates an SEC client. baseURL is configurable so tests can use a
// local fake provider while production uses DefaultBaseURL.
func NewClient(baseURL, userAgent string, httpClient *http.Client) (*Client, error) {
	normalizedBaseURL := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if normalizedBaseURL == "" {
		return nil, fmt.Errorf("%w: base URL is required", ErrInvalidConfiguration)
	}
	if _, err := url.ParseRequestURI(normalizedBaseURL); err != nil {
		return nil, fmt.Errorf("%w: base URL: %w", ErrInvalidConfiguration, err)
	}

	normalizedUserAgent := strings.TrimSpace(userAgent)
	if normalizedUserAgent == "" {
		return nil, fmt.Errorf("%w: user agent is required", ErrInvalidConfiguration)
	}
	if httpClient == nil {
		return nil, fmt.Errorf("%w: HTTP client is required", ErrInvalidConfiguration)
	}

	return &Client{
		baseURL:    normalizedBaseURL,
		userAgent:  normalizedUserAgent,
		httpClient: httpClient,
	}, nil
}

// Recent8K returns up to limit recent 8-K records for a ten-digit CIK.
func (c *Client) Recent8K(ctx context.Context, cik string, limit int) ([]Filing, error) {
	if err := validateCIK(cik); err != nil {
		return nil, err
	}
	if limit < 1 {
		return nil, fmt.Errorf("%w: must be at least one", ErrInvalidLimit)
	}

	requestURL, err := url.JoinPath(c.baseURL, "submissions", "CIK"+cik+".json")
	if err != nil {
		return nil, fmt.Errorf("%w: build submissions URL: %w", ErrRequestFailed, err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return nil, fmt.Errorf("%w: build request: %w", ErrRequestFailed, err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.userAgent)

	response, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrRequestFailed, err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%w: status %s", ErrRequestFailed, response.Status)
	}

	var payload submissionsPayload
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return nil, fmt.Errorf("%w: decode JSON: %w", ErrInvalidPayload, err)
	}
	return payload.Filings.Recent.normalized8K(cik, limit)
}

// submissionsPayload mirrors only the provider fields this client needs. It is
// unexported so no caller can accidentally depend on SEC's JSON shape.
type submissionsPayload struct {
	Filings struct {
		Recent recentFilingsPayload `json:"recent"`
	} `json:"filings"`
}

type recentFilingsPayload struct {
	AccessionNumbers []string `json:"accessionNumber"`
	Forms            []string `json:"form"`
	FilingDates      []string `json:"filingDate"`
}

func (recent recentFilingsPayload) normalized8K(cik string, limit int) ([]Filing, error) {
	if len(recent.AccessionNumbers) != len(recent.Forms) ||
		len(recent.Forms) != len(recent.FilingDates) {
		return nil, fmt.Errorf("%w: filing fields have different lengths", ErrInvalidPayload)
	}

	filings := make([]Filing, 0, limit)
	for index, form := range recent.Forms {
		if form != "8-K" {
			continue
		}

		accessionNumber := recent.AccessionNumbers[index]
		if accessionNumber == "" {
			return nil, fmt.Errorf("%w: 8-K is missing accession number", ErrInvalidPayload)
		}
		filingDate, err := time.Parse(time.DateOnly, recent.FilingDates[index])
		if err != nil {
			return nil, fmt.Errorf("%w: invalid filing date: %w", ErrInvalidPayload, err)
		}

		filings = append(filings, Filing{
			CIK:             cik,
			AccessionNumber: accessionNumber,
			Form:            form,
			FilingDate:      filingDate,
		})
		if len(filings) == limit {
			break
		}
	}

	return filings, nil
}

func validateCIK(cik string) error {
	if len(cik) != 10 {
		return fmt.Errorf("%w: must contain exactly ten digits", ErrInvalidCIK)
	}
	for _, character := range cik {
		if character < '0' || character > '9' {
			return fmt.Errorf("%w: must contain only digits", ErrInvalidCIK)
		}
	}
	return nil
}
