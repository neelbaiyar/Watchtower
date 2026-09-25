# Watchtower Product Brief

## Product Promise

Watchtower helps self-directed technology investors decide which companies on
their watchlist deserve deeper research by ranking companies using recent news
and transparent importance signals, with every result linked to its supporting
sources.

## First User

A self-directed investor who researches technology companies over a weeks-to-
months time horizon and needs help prioritizing limited research time.

The first user is not a professional day trader, institutional trading desk, or
person seeking an automated trading decision.

## Recurring Decision

Which companies on the user's technology watchlist deserve deeper research now?

Watchtower supports research prioritization. It does not determine whether a
security is a worthwhile investment and does not recommend buying or selling.

## Problem

Relevant company developments are distributed across many sources, repeatedly
reported, and mixed with low-value coverage. A self-directed investor can spend
substantial time finding, checking, and prioritizing news before beginning the
actual investment research.

## Smallest Useful Product Behavior

Given a small watchlist and a small collection of recent, source-linked company
news, Watchtower presents a ranked research queue. Each result shows the evidence
that contributed to its position so the user can inspect the sources rather than
trusting an unexplained score.

The first implementation may use manually created news records and transparent
rules. Machine learning is not required to prove this behavior.

## Initial Success Measures

The first usable vertical slice succeeds when:

- A user can retrieve a ranked research queue for a small technology watchlist.
- Every ranked result links to its supporting news record or source.
- The reason for each result's position is visible and understandable.
- Repeated runs with the same inputs produce reproducible results.
- The learner can explain the request flow, ranking rule, data representation,
  and limitations without relying on generated code.

These measures validate product behavior and learning. They do not claim that
the ranking predicts investment returns.

## Initial Non-Goals

- Buy, sell, or hold recommendations.
- Predictions of positive or negative returns.
- Real-time or intraday trading signals.
- Automated execution or paper trading.
- A trained ML model.
- Live ingestion from every relevant source.
- Autonomous agents, RAG, embeddings, or a knowledge graph.
- A complete frontend, authentication system, or cloud deployment.

## Why Predictive Trading Can Wait

News can provide evidence that a company deserves attention, but it cannot by
itself prove a future positive or negative return. A responsible predictive
system would additionally need a precise target and time horizon, point-in-time
data, controls against leakage and coverage bias, suitable market and company
features, chronological evaluation, uncertainty analysis, and evidence that it
outperforms a simpler baseline after operational costs.

Building the inspectable research-ranking behavior first creates the data,
interfaces, and evaluation habits that a later ML experiment would need.

