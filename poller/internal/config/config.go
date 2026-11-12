// Package config reads the non-secret shape of a poller run from the environment.
package config

import (
	"errors"
	"fmt"
	"strings"
)

const (
	// These names form the public local-runtime configuration contract. Values
	// live in an ignored .env file, never in committed Go source.
	DatabaseURLVariable  = "WATCHTOWER_POLLER_DATABASE_URL"
	CIKsVariable         = "WATCHTOWER_POLLER_CIKS"
	SECUserAgentVariable = "WATCHTOWER_SEC_USER_AGENT"
	DefaultFilingLimit   = 5
)

var ErrInvalidConfiguration = errors.New("invalid poller configuration")

// LookupEnvironment makes configuration parsing testable without changing the
// real process environment.
type LookupEnvironment func(string) (string, bool)

type Config struct {
	// Config holds validated values only. Parsing converts the convenient
	// comma-separated environment representation into a safe Go slice once.
	DatabaseURL  string
	SECUserAgent string
	CIKs         []string
	FilingLimit  int
}

func FromEnvironment(lookup LookupEnvironment) (Config, error) {
	databaseURL, err := requiredValue(lookup, DatabaseURLVariable)
	if err != nil {
		return Config{}, err
	}
	userAgent, err := requiredValue(lookup, SECUserAgentVariable)
	if err != nil {
		return Config{}, err
	}
	rawCIKs, err := requiredValue(lookup, CIKsVariable)
	if err != nil {
		return Config{}, err
	}

	// A map with empty values is Go's lightweight "set" pattern. It prevents
	// the same company from being polled twice in one requested run.
	seen := make(map[string]struct{})
	ciks := make([]string, 0)
	for _, rawCIK := range strings.Split(rawCIKs, ",") {
		cik := strings.TrimSpace(rawCIK)
		if err := validateCIK(cik); err != nil {
			return Config{}, err
		}
		if _, duplicate := seen[cik]; duplicate {
			return Config{}, fmt.Errorf("%w: duplicate CIK %q", ErrInvalidConfiguration, cik)
		}
		seen[cik] = struct{}{}
		ciks = append(ciks, cik)
	}

	return Config{
		DatabaseURL:  databaseURL,
		SECUserAgent: userAgent,
		CIKs:         ciks,
		FilingLimit:  DefaultFilingLimit,
	}, nil
}

func requiredValue(lookup LookupEnvironment, name string) (string, error) {
	// Trim here rather than at every caller so whitespace-only environment
	// values behave exactly like missing values.
	value, present := lookup(name)
	value = strings.TrimSpace(value)
	if !present || value == "" {
		return "", fmt.Errorf("%w: %s is required", ErrInvalidConfiguration, name)
	}
	return value, nil
}

func validateCIK(cik string) error {
	// CIKs are stored as strings to preserve leading zeroes required by SEC URL
	// paths and database validation, even though their characters are digits.
	if len(cik) != 10 {
		return fmt.Errorf("%w: CIK %q must contain exactly ten digits", ErrInvalidConfiguration, cik)
	}
	for _, character := range cik {
		if character < '0' || character > '9' {
			return fmt.Errorf("%w: CIK %q must contain only digits", ErrInvalidConfiguration, cik)
		}
	}
	return nil
}
