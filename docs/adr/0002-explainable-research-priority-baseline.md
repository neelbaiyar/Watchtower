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

- recent 8-K filing activity;
- number of recent ticker-associated headlines; and
- magnitude of the latest daily price movement, regardless of direction.

The response includes the level, score, source-linked evidence, and a template
based explanation. It explicitly states that it is not investment advice or a
prediction of price direction.

The application depends on a small `ResearchSignalEngine` contract. The public
transparent baseline implements that contract. A future private or trained
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

## Guardrails

- Never label the result as buy, sell, hold, bullish, bearish, or predictive.
- Preserve source provenance for every evidence item.
- Keep the public baseline deterministic and free of private heuristics.
- Introduce a trained model only with a separate evaluation and validation plan.
