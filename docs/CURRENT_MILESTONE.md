# Current Milestone

This file is the scope boundary for active work. Update it when evidence
changes, not whenever a new idea appears.

## Milestone 9: Explainable Research-Priority Signal

**Status:** Complete — ready for review

### Goal

Turn a Watchtower company snapshot into a transparent five-level research
priority signal. The signal tells a user which companies deserve deeper
research now; it does not predict price direction or recommend buying, selling,
or holding a security.

### User and System Value

The existing snapshot collects evidence but leaves prioritization entirely to
the user. A deterministic signal makes that prioritization visible and
repeatable while preserving every source link needed to inspect its reasoning.

### Concepts

- A deterministic baseline produces the same output for the same input.
- An ordinal signal places an item into an ordered category without claiming a
  probability or prediction.
- Evidence is the source-linked fact contributing to a derived result.
- A typed interface separates callers from a particular engine implementation.
- A pure function can be tested without HTTP, databases, clocks, or providers.

### Architecture Boundary

```text
Watchtower-owned snapshot evidence
    -> ResearchSignalEngine contract
    -> TransparentResearchSignalEngine baseline
    -> level, numeric attention score, evidence, deterministic explanation
    -> public Watchtower response
```

The engine receives normalized Watchtower records, never raw vendor JSON. Its
public baseline stays in this repository. A later private or trained engine may
implement the same contract without changing API callers.

### Options Considered

1. **LLM-generated interpretation:** flexible but non-deterministic, requires
   prompt/version/evaluation work, and is unnecessary for this first signal.
2. **Trained price-prediction model:** potentially appropriate for a later ML
   milestone, but requires labels, point-in-time data, backtesting, and a
   rigorous evaluation plan.
3. **Transparent rule baseline:** selected. It is reproducible, source-linked,
   safe to describe, and establishes the interface that later models must beat.

### Selected Design

Calculate a bounded 0–100 **research-attention score** from observable facts:
recent 8-K activity, headline count, and the magnitude—not direction—of the
latest daily price movement. Map that score to five attention levels and return
the contributing evidence plus a deterministic explanation.

The score is an operational prioritization aid. Positive and negative price
moves can both increase attention because either may justify research.

### Files

- `docs/adr/0002-explainable-research-priority-baseline.md`
- `src/watchtower/signals/contracts.py`
- `src/watchtower/signals/transparent.py`
- `src/watchtower/schemas/company_snapshot.py`
- `src/watchtower/services/company_snapshot.py`
- `tests/signals/test_transparent.py`
- `tests/services/test_company_snapshot_service.py`
- `tests/schemas/test_company_snapshot.py`
- `docs/CURRENT_MILESTONE.md`
- `README.md`

### Build Order

- [x] Define the public signal and evidence schemas plus the engine contract.
- [x] Implement and unit-test the pure transparent baseline.
- [x] Compose the signal into the existing snapshot service.
- [x] Verify the API response exposes source-linked evidence and an honest
      limitation statement.
- [x] Document the signal inputs, weights, limitations, and local run path.
- [x] Run Go and Python quality checks plus a staged secret scan.

### Smallest Unfinished Piece

Define a stable, source-linked signal contract and test its five-level boundary
behavior before integrating it into the live FastAPI response.

### Acceptance Criteria

- [x] The public response names five research-priority levels without using
      buy, sell, hold, bullish, bearish, or prediction language.
- [x] The same normalized evidence produces the same score, level, evidence,
      and explanation.
- [x] Every evidence item identifies its source and links to an underlying
      filing or article when one exists.
- [x] The baseline uses no LLM, model weights, private dataset, or live call.
- [x] The service depends on a typed signal-engine contract, not directly on
      the transparent implementation.
- [x] Unit, service, schema, API, lint, format, and secret checks pass.

### Explicitly Out of Scope

- Price-direction, return, or investment recommendations.
- LLM summaries, sentiment inference, embeddings, or a trained ML model.
- Historical labels, backtesting, model validation, or evaluation datasets.
- Scheduled polling, database watchlists, cache-backed reads, or the local UI.
- A private engine implementation or any proprietary logic in this repository.
