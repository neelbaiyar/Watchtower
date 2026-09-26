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

	ctx, cancel := context.WithCancel(context.Background())
	var output bytes.Buffer
	logger := log.New(&output, "", 0)
	result := make(chan error, 1)

	go func() {
		result <- run(ctx, logger)
	}()

	// The test controls cancellation directly, so it stays deterministic and
	// does not need to send a real interrupt to the test process.
	cancel()

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
