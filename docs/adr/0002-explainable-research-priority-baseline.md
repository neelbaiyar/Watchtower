# ADR 0002: Explainable Research-Priority Baseline

- **Status:** Accepted
- **Date:** 2026-11-12
- **Decision owners:** Watchtower project

## Context

Watchtower already assembles source-grounded filing, price, and headline data.
The first product need is to help a user decide which company deserves deeper
research, not to predict a future return. The public/private boundary in ADR
0001 requires the first scoring milestone to define a typed contract and a
runnable public baseline before any private implementation exists.

## Decision

Expose a five-level, deterministic research-priority signal. The transparent
baseline calculates a bounded attention score from normalized Watchtower
evidence:

- 8-K filings filed in the 30 days before the snapshot;
- ticker-associated headlines published in the 7 days before the snapshot; and
- magnitude of the latest daily price movement, regardless of direction.

The response includes the level, score, source-linked evidence, and a template
based explanation. It explicitly states that it is not investment advice or a
prediction of price direction.

The application depends on a small `ResearchSignalEngine` contract. Its input
carries each filing's date, each headline's publication time, and the `as_of`
instant the evidence was gathered. Engines do not read a clock, so the same
input always produces the same result. The public transparent baseline
implements that contract. A future private or trained
engine may implement the same contract through dependency injection after it is
developed outside this repository.

## Options Considered

### LLM Interpretation

An LLM could generate fluent descriptions, but it would add non-determinism,
prompt-versioning, cost, and evaluation requirements. It would also blur the
line between source facts and model interpretation. Rejected for this
milestone.

### Trained Predictive Model

A prediction model would need a defined target, point-in-time historical data,
leakage controls, chronological validation, uncertainty analysis, and
backtesting. Those are not prerequisites for an explainable research queue.
Deferred to a separate ML milestone.

### Transparent Rule Baseline

Rules make every output reproducible and inspectable. They are suitable for a
public repository and establish an interface and baseline that a future model
must outperform. Selected.

## Consequences

### Benefits

- Users can inspect the exact facts that caused a higher research priority.
- Tests can cover every scoring boundary without provider calls.
- The public repository demonstrates safe derived-data design without claiming
  investment-prediction capability.
- A later engine can be substituted without rewriting API callers.

### Costs and Risks

- Structural evidence does not establish cause, sentiment, or future returns.
- Rule weights encode a simple product policy and may need revisiting with user
  feedback.
- Headline count is a proxy for attention, not a measure of importance.

## Revision: 2026-11-13, Date Windows

The first version counted every filing and headline a provider returned.
Providers return their newest items regardless of age, so nearly any active
company received five filings (40 points) and three headlines (18 points). A
score of 58 is already `elevated_attention` before price is considered, which
meant the signal could not separate a busy company from a quiet one.

The baseline now counts a filing only when it was filed within 30 days of the
snapshot and a headline only when it was published within 7 days. Both
boundaries are inclusive.

- **30 days for filings:** an 8-K reports a material event, and a month is long
  enough to cover the follow-up research that event deserves while excluding
  last quarter's routine filings.
- **7 days for headlines:** news attention fades much faster than a filing's
  relevance, and the provider returns at most three headlines per request.

Point values and level thresholds are unchanged. The public response schema is
unchanged; only the evidence summaries now name the window. The engine input
contract changed from bare URL lists to dated facts plus `as_of`, which any
replacement engine must also accept.

Filing dates have no time zone, so they are compared as whole calendar days
against the UTC date of the snapshot. Near midnight UTC this can shift the
boundary by one day. The windows are product policy, not measured optima, and
should be revisited with user feedback.

## Guardrails

- Never label the result as buy, sell, hold, bullish, bearish, or predictive.
- Preserve source provenance for every evidence item.
- Keep the public baseline deterministic and free of private heuristics.
- Introduce a trained model only with a separate evaluation and validation plan.
