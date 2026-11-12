// This package uses Go's local HTTP test server as a controlled SEC boundary.
package edgar

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestRecent8KNormalizesExpectedFilings(t *testing.T) {
	t.Parallel()

	// The handler verifies Watchtower's outbound request before returning a
	// minimal SEC-shaped response; no request leaves this computer.
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet {
			t.Errorf("method = %q, want GET", request.Method)
		}
		if request.URL.Path != "/submissions/CIK0000320193.json" {
			t.Errorf("path = %q, want CIK submissions path", request.URL.Path)
		}
		if request.Header.Get("User-Agent") != "Watchtower test@example.com" {
			t.Errorf("User-Agent = %q, want configured identity", request.Header.Get("User-Agent"))
		}
		if request.Header.Get("Accept") != "application/json" {
			t.Errorf("Accept = %q, want application/json", request.Header.Get("Accept"))
		}

		response.Header().Set("Content-Type", "application/json")
		_, _ = response.Write([]byte(`{
			"filings": {"recent": {
				"accessionNumber": ["0001", "0002", "0003"],
				"form": ["10-K", "8-K", "8-K"],
				"filingDate": ["2026-09-20", "2026-09-21", "2026-09-22"]
			}}
		}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "Watchtower test@example.com", server.Client())
	if err != nil {
		t.Fatalf("NewClient() error = %v", err)
	}

	filings, err := client.Recent8K(context.Background(), "0000320193", 2)
	if err != nil {
		t.Fatalf("Recent8K() error = %v", err)
	}
	if len(filings) != 2 {
		t.Fatalf("len(filings) = %d, want 2", len(filings))
	}

	wantDate := time.Date(2026, time.September, 21, 0, 0, 0, 0, time.UTC)
	// The assertion compares a Watchtower Filing, proving raw SEC arrays do not
	// escape the client boundary.
	if filings[0] != (Filing{
		CIK:             "0000320193",
		AccessionNumber: "0002",
		Form:            "8-K",
		FilingDate:      wantDate,
	}) {
		t.Errorf("first filing = %#v, want normalized first 8-K", filings[0])
	}
}

func TestRecent8KReturnsRequestErrorForNonSuccessStatus(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		response.WriteHeader(http.StatusTooManyRequests)
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "Watchtower test@example.com", server.Client())
	if err != nil {
		t.Fatalf("NewClient() error = %v", err)
	}

	_, err = client.Recent8K(context.Background(), "0000320193", 1)
	if !errors.Is(err, ErrRequestFailed) {
		t.Fatalf("Recent8K() error = %v, want ErrRequestFailed", err)
	}
}
