// These tests parse maps, not the real environment, so they are isolated from
// a developer's local secrets and shell configuration.
package config

import (
	"errors"
	"testing"
)

func TestFromEnvironmentReadsConfiguredCIKs(t *testing.T) {
	t.Parallel()

	// Surrounding whitespace is normal in copied .env values and should not
	// change the CIKs the poller uses.
	settings, err := FromEnvironment(lookupFromMap(map[string]string{
		DatabaseURLVariable:  "postgres://watchtower:password@127.0.0.1:5432/watchtower?sslmode=disable",
		SECUserAgentVariable: "Watchtower test@example.com",
		CIKsVariable:         " 0000320193,0000789019 ",
	}))
	if err != nil {
		t.Fatalf("FromEnvironment() error = %v", err)
	}

	if len(settings.CIKs) != 2 || settings.CIKs[0] != "0000320193" || settings.CIKs[1] != "0000789019" {
		t.Errorf("CIKs = %#v, want normalized configured CIKs", settings.CIKs)
	}
	if settings.FilingLimit != DefaultFilingLimit {
		t.Errorf("FilingLimit = %d, want %d", settings.FilingLimit, DefaultFilingLimit)
	}
}

func TestFromEnvironmentRejectsMissingOrDuplicateCIKs(t *testing.T) {
	t.Parallel()

	base := map[string]string{
		DatabaseURLVariable:  "postgres://watchtower:password@127.0.0.1:5432/watchtower?sslmode=disable",
		SECUserAgentVariable: "Watchtower test@example.com",
	}

	// Table cases keep every invalid input mapped to the same owned error type.
	for name, ciks := range map[string]string{
		"missing":   "",
		"duplicate": "0000320193,0000320193",
		"malformed": "not-a-cik",
	} {
		t.Run(name, func(t *testing.T) {
			values := make(map[string]string, len(base)+1)
			for key, value := range base {
				values[key] = value
			}
			values[CIKsVariable] = ciks

			_, err := FromEnvironment(lookupFromMap(values))
			if !errors.Is(err, ErrInvalidConfiguration) {
				t.Fatalf("FromEnvironment() error = %v, want ErrInvalidConfiguration", err)
			}
		})
	}
}

func lookupFromMap(values map[string]string) LookupEnvironment {
	// This adapter gives production parsing the same (value, present) contract
	// as os.LookupEnv while leaving the real process environment untouched.
	return func(name string) (string, bool) {
		value, present := values[name]
		return value, present
	}
}
