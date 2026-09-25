# ADR 0001: Public Interface, Private Consequence Engine

- **Status:** Accepted
- **Date:** 2026-09-22
- **Decision owners:** Watchtower project

## Context

Watchtower is both a portfolio project and a potential differentiated product.
Recruiters and engineers should be able to inspect meaningful backend work, run
the application, review its tests, and evaluate its architecture. Publishing the
logic that produces proprietary consequence rankings, however, could disclose
the project's unique value.

This boundary must be decided before the first public commit because deleting a
file in a later commit does not remove it from Git history.

## Decision

Use a public-interface/private-implementation boundary for consequence scoring.

The public application will eventually depend on a small typed interface, such
as a `ConsequenceEngine`, that accepts a documented input schema and returns a
documented result schema. The API and application layers will depend on this
interface rather than on proprietary scoring code.

```text
Public clients
      |
Public FastAPI service
      |
Public ConsequenceEngine contract
      |-----------------------------|
Public transparent baseline     Private adapter or service
```

The public baseline will be deterministic, explainable, and sufficient to keep
the repository runnable. A private implementation may later be supplied through
dependency injection, a private package, or a separately deployed service. Both
implementations must satisfy the same public contract tests.

## Public Repository Contents

The public repository will include:

- API routes, OpenAPI documentation, schemas, and clients.
- Ingestion, normalization, persistence, scheduling, and non-proprietary service
  orchestration.
- Database migrations and non-sensitive models.
- Error handling, security controls, observability, and operational tooling.
- Unit, integration, API, and contract tests.
- CI/CD and reproducible local-development configuration.
- Architecture documentation and a transparent baseline ranker.

## Private Contents

The public repository will not contain:

- Proprietary ranking, consequence-scoring, or feature-engineering logic.
- Private model weights, labels, evaluation sets, or training data.
- Sensitive prompts or research workflows that reveal proprietary behavior.
- Licensed datasets, secrets, credentials, or customer information.

Private assets will live in a separate access-controlled repository, package
registry, artifact store, or service. They must never be temporarily committed
to the public repository.

## Options Considered

### Publish the Entire Implementation

This maximizes transparency but exposes proprietary logic and makes later
removal unreliable because Git retains history. Rejected.

### Publish Only a Frontend Wrapper

This protects intellectual property but fails the portfolio objective: reviewers
cannot evaluate meaningful backend, data, testing, or operational engineering.
Rejected.

### Keep Private Code in an Ignored Folder in the Public Checkout

This is simple locally, but `.gitignore` is a convenience rather than an access-
control system. Accidental staging, copying, patching, or history leakage remains
too easy. Rejected as the primary boundary.

### Separate the Private Implementation Behind a Public Contract

This preserves a substantial public system, supports local execution through a
baseline, and isolates proprietary logic. It adds contract versioning and later
integration complexity, but those costs arise only when a private implementation
actually exists. Accepted.

## Consequences

### Benefits

- The public repository remains technically substantial and interview-worthy.
- Proprietary behavior can evolve without changing public callers when the
  contract remains stable.
- Contract tests make public and private implementations substitutable.
- A transparent baseline supports local development, CI, demos, and evaluation.
- Private code is isolated before Git history exists.

### Costs and Risks

- Public and private implementations must coordinate schema versions.
- A remote private service would add latency, availability, authentication, and
  deployment concerns.
- An interface can become an unnecessary abstraction if designed before real
  scoring inputs and outputs are understood.
- Public fixtures must be reviewed so they do not disclose private datasets or
  expected proprietary outputs.

## Incremental Application

Milestone 1 contains no consequence-ranking logic, so it does not add an engine
interface or private service. It delivers the public, ticker-driven company
snapshot endpoint defined in `docs/CURRENT_MILESTONE.md`.

When a future milestone first introduces consequence scoring:

1. Define the smallest typed input and output contract from observed needs.
2. Implement a transparent public baseline.
3. Add contract tests against the public baseline.
4. Create any proprietary implementation only in a separate private location.
5. Select the implementation through dependency injection or configuration.
6. Verify public API behavior without requiring private assets.

## Git-History Rule

Assume that anything staged or committed to the public repository may remain
recoverable indefinitely. If ownership or sensitivity is uncertain, stop before
`git add`. `.gitignore` provides defense in depth but is not the confidentiality
boundary.
