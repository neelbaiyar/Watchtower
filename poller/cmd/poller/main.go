// Command poller runs Watchtower's long-lived background polling process.
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	logger := log.New(os.Stdout, "watchtower-poller: ", log.LstdFlags)

	// Convert terminal interrupts and container shutdown requests into the same
	// cancellation signal that future HTTP and database work will receive.
	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	if err := run(ctx, logger); err != nil {
		logger.Printf("stopped with error: %v", err)
		os.Exit(1)
	}
}

// run owns the poller's lifecycle independently from operating-system wiring,
// allowing tests to request shutdown without sending a real process signal.
func run(ctx context.Context, logger *log.Logger) error {
	logger.Println("started")

	// Waiting on the context blocks without repeatedly checking a flag or
	// consuming CPU. Later work will receive this same context.
	<-ctx.Done()

	logger.Println("shutdown requested")
	return nil
}
