// This test exercises the process lifecycle without starting real polling.
package main

import (
	"bytes"
	"context"
	"log"
	"strings"
	"testing"
	"time"
)

func TestRunStopsWhenContextIsCancelled(t *testing.T) {
	t.Parallel()

	// A cancelable context is the test-friendly stand-in for a user pressing
	// Control-C. No operating-system signal needs to reach `go test`.
	ctx, cancel := context.WithCancel(context.Background())
	var output bytes.Buffer
	logger := log.New(&output, "", 0)
	result := make(chan error, 1)

	// run blocks, so run it concurrently and collect its eventual return value.
	go func() {
		result <- run(ctx, logger)
	}()

	// The test controls cancellation directly, so it stays deterministic and
	// does not need to send a real interrupt to the test process.
	cancel()

	// The timeout converts a stuck shutdown into a clear failed test instead of
	// letting the test suite hang forever.
	select {
	case err := <-result:
		if err != nil {
			t.Fatalf("run() returned an unexpected error: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("run() did not stop after cancellation")
	}

	for _, message := range []string{"started", "shutdown requested"} {
		if !strings.Contains(output.String(), message) {
			t.Errorf("expected log output to contain %q", message)
		}
	}
}
