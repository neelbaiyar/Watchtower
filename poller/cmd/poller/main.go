// Command poller runs Watchtower's long-lived background polling process.
package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/neelbaiyar/Watchtower/poller/internal/config"
	"github.com/neelbaiyar/Watchtower/poller/internal/edgar"
	"github.com/neelbaiyar/Watchtower/poller/internal/pollrun"
	"github.com/neelbaiyar/Watchtower/poller/internal/storage"
)

func main() {
	// Flags are parsed before configuration or network dependencies are built.
	// This lets the default command stay safe and idle.
	once := flag.Bool("once", false, "poll configured CIKs once, then exit")
	flag.Parse()

	logger := log.New(os.Stdout, "watchtower-poller: ", log.LstdFlags)

	// Convert terminal interrupts and container shutdown requests into the same
	// cancellation signal that future HTTP and database work will receive.
	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	var err error
	if *once {
		// `--once` is the explicit opt-in for outward SEC and database work.
		err = runOnceFromEnvironment(ctx, logger, os.LookupEnv)
	} else {
		// The default mode proves lifecycle handling without polling by surprise.
		err = run(ctx, logger)
	}
	if err != nil {
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

func runOnceFromEnvironment(
	ctx context.Context,
	logger *log.Logger,
	lookup config.LookupEnvironment,
) error {
	// Parse all configuration before opening either provider or database
	// connections, so a malformed local setup cannot make a partial poll.
	settings, err := config.FromEnvironment(lookup)
	if err != nil {
		return err
	}

	// The timeout bounds one provider request. Context cancellation still stops
	// the request earlier when the process receives a shutdown signal.
	httpClient := &http.Client{Timeout: 10 * time.Second}
	secClient, err := edgar.NewClient(edgar.DefaultBaseURL, settings.SECUserAgent, httpClient)
	if err != nil {
		return err
	}

	// A pool manages reusable database connections; it is closed when this
	// bounded one-shot command finishes.
	pool, err := storage.Connect(ctx, settings.DatabaseURL)
	if err != nil {
		return err
	}
	defer pool.Close()

	recorder, err := storage.NewPostgresSeenStore(pool)
	if err != nil {
		return err
	}

	// The runner receives already-built dependencies. It therefore coordinates
	// work without knowing about environment variables, HTTP, or SQL details.
	return pollrun.RunOnce(ctx, settings.CIKs, settings.FilingLimit, secClient, recorder, logger)
}
