# Watchtower Project Vision

## Vision

Watchtower will become a production-quality, AI-powered technology news and
market intelligence platform. It will help a focused user turn fragmented,
duplicated reporting into source-grounded stories, searchable intelligence, and
useful market context.

The project has two equally important products:

1. A trustworthy intelligence application.
2. A deliberate learning environment for developing software engineering, AI
   engineering, and machine-learning judgment.

Finishing features is not sufficient. The engineer building Watchtower should be
able to explain its architecture, defend its tradeoffs, operate it, diagnose its
failures, evaluate its AI behavior, and extend it without relying on generated
code they do not understand.

## Product Direction

The initial product direction is a watchlist-centered system that:

- Collects technology reporting from selected, trustworthy sources.
- Preserves source attribution and article provenance.
- Normalizes articles and groups duplicate coverage into stories.
- Extracts relevant companies, products, technologies, and themes.
- Produces concise, source-grounded AI summaries.
- Supports filtering, lexical search, and eventually semantic search.
- Connects stories to public-company or industry context without presenting
  correlation or model speculation as fact.
- Lets users maintain focused watchlists instead of consuming an undifferentiated
  global feed.

The exact first user, initial sectors, source list, and meaning of “market
intelligence” remain product decisions to make before implementation.

## Learning Outcomes

### Software Engineering

- Requirements, user stories, scope, and acceptance criteria.
- Git workflows and reviewable change sets.
- Modular architecture and dependency boundaries.
- HTTP, API design, validation, and error contracts.
- Relational modeling, SQL, transactions, indexes, and migrations.
- Background jobs, retries, idempotency, and failure recovery.
- Testing strategy across unit, integration, contract, and browser layers.
- Security, observability, performance, deployment, and incident response.

### AI Engineering

- Structured model outputs and schema validation.
- Prompt and model versioning.
- Retrieval, embeddings, ranking, and source grounding.
- Evaluation datasets, quality metrics, and regression testing.
- Latency, token cost, rate limits, retries, and fallbacks.
- Human review, uncertainty, provenance, and responsible presentation.

### Machine Learning

- Establishing non-ML baselines before training models.
- Creating and governing labeled datasets.
- Feature construction and leakage prevention.
- Training and evaluation with PyTorch and Hugging Face when justified.
- Offline metrics versus real user outcomes.
- Experiment tracking, reproducibility, model serving, and monitoring.

## Engineering Principles

1. Start with the user decision, not the technology.
2. Build a modular monolith before considering microservices.
3. Prefer simple, observable systems over clever, opaque systems.
4. Preserve raw inputs and provenance so derived results can be reproduced.
5. Treat AI output as fallible derived data, never unquestioned truth.
6. Make quality measurable with tests, datasets, and explicit acceptance criteria.
7. Introduce infrastructure only when its problem has been observed or clearly
   established.
8. Make the smallest production-shaped increment that teaches a reusable concept.
9. Document consequential decisions and revisit them when assumptions change.
10. Keep the application continuously runnable as it grows.
11. Protect the current milestone from the long-term vision: finish the smallest
    useful working slice before expanding scope.
12. Keep portfolio-visible engineering public while isolating proprietary
    consequence-ranking behavior behind a stable, testable interface.

## Portfolio and Intellectual-Property Boundary

The public Watchtower repository should demonstrate substantial backend and AI
engineering: API contracts, schemas, ingestion, persistence, tests, observability,
CI/CD, documentation, and a transparent baseline must remain visible and
runnable. It must not be reduced to a frontend wrapper around a hidden product.

Proprietary consequence-ranking logic, model weights, sensitive prompts,
heuristics, private datasets, and licensed data remain outside the public
repository. When that logic exists, the public application will communicate with
it through a small typed interface or service contract. A public baseline will
implement the same contract so contributors and recruiters can run, inspect, and
test the system without private assets.

This boundary is an application of abstraction: callers depend on what the
component promises, not how a particular implementation produces its result.
The boundary is recorded now to prevent accidental Git-history disclosure, but
it will not be implemented until a scoring milestone creates the concrete need.

## Anti-Fantasy Constraint

The long-term vision is a direction, not a backlog and not a promise that every
idea must be built. Watchtower must not become an enormous future identity that
is more enjoyable to imagine than to implement.

At any moment, the project should be able to answer:

- What is the single active milestone?
- What is the smallest unfinished piece?
- What observable evidence will prove that piece is finished?
- What did the engineer learn by completing it?

If those answers are unclear, the correct next action is to reduce scope—not to
add architecture. Future capabilities remain optional until the working system
creates a concrete need for them.

## Initial Non-Goals

Until the core pipeline is reliable, Watchtower will not attempt to be:

- A universal crawler for every technology publication.
- An autonomous trading system or source of financial advice.
- A stock-price prediction engine.
- A collection of unsupervised agents with unclear responsibilities.
- A microservice system built for hypothetical scale.
- A custom-trained language model without a dataset, baseline, and evaluation
  plan.

## Definition of Production Quality

For this project, “production quality” means more than deployment. A production-
quality increment has:

- A clear owner and responsibility boundary.
- Validated inputs and explicit failure behavior.
- Appropriate automated tests.
- Secure configuration and secret handling.
- Useful logs, metrics, and health signals.
- Reproducible local and CI environments.
- Documented setup and operational procedures.
- Measured AI quality where model behavior affects the user.
- Accessibility and understandable loading, empty, and error states.

## Provisional Technical Direction

The expected starting direction is:

- FastAPI for a typed Python API.
- PostgreSQL for relational data and initial search capabilities.
- A modern TypeScript web application for the user interface.
- Docker for development dependencies and reproducible environments.
- GitHub Actions for continuous integration.
- A provider-neutral AI integration boundary.
- PyTorch and Hugging Face only when a well-defined ML problem and evaluation
  dataset justify model development.

Every major selection requires a short tradeoff analysis and, when consequential,
an architecture decision record.

## Open Product Decisions

Before repository scaffolding begins, decide:

1. Who is the first user?
2. What recurring decision should Watchtower improve for that user?
3. Which two or three technology areas belong in the MVP?
4. What does “market intelligence” mean in the first release?
5. Which initial sources are trustworthy, accessible, and legally usable?
6. What measurable behavior makes the MVP useful?
7. What information must always link back to its original source?

These answers will become the first product brief and define the MVP boundary.
