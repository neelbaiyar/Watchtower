# Current Milestone

This file is the scope boundary for active work. Update it when evidence changes,
not whenever a new idea appears.

## Milestone 1: Real Company Snapshot Demo

**Status:** Complete  
**Target:** Monday night, September 28, 2026

### Goal

Build the smallest real Watchtower vertical slice that can:

1. Start locally as a FastAPI application.
2. Expose interactive OpenAPI documentation at `/docs`.
3. Accept any supported ticker as input, including a common ticker and `HPE`.
4. Return Watchtower-owned JSON composed from real SEC filings, market-price
   data, and free headline metadata.

The candidate aggregate route is:

```http
GET /companies/{ticker}/snapshot
```

The path is a low-risk implementation decision and may change only if provider
or schema work reveals a concrete problem.

### Architecture Boundary

```text
FastAPI route
    -> company snapshot service
        -> SEC EDGAR client
        -> price client (yfinance adapter)
        -> news client (free provider adapter)
    -> Watchtower Pydantic response schema
```

- Routes validate HTTP input and translate known application errors.
- The service composes provider-independent Watchtower records.
- Provider clients own external API details and never expose raw payloads.
- Ticker is always runtime input; no implementation is specific to HPE.
- No consequence engine, ranking model, knowledge graph, or proprietary logic is
  part of this milestone.

### Build Order

- [x] SEC EDGAR client: implemented, unit-verified, and live-smoke-verified for
      `AAPL` and `HPE`.
- [x] Price client wrapping yfinance, unit-verified and live-smoke-verified for
      `AAPL` and `HPE`.
- [x] Marketaux news/headline client, unit-verified and live-smoke-verified for
      `AAPL` and `HPE`.
- [x] Public Watchtower Pydantic schemas with strict validation, provenance,
      and serialization tests.
- [x] Company snapshot service composing the three clients, unit-verified and
      live-smoke-verified for `AAPL` and `HPE`.
- [x] Thin FastAPI route and `/docs` application metadata.
- [x] Basic provider and input error handling.
- [x] Important unit, service, and API tests.
- [x] README setup and demo instructions.

### Smallest Unfinished Piece

None. Milestone 1 is complete. Do not begin polling, caching, ML, scoring, or
another feature until the repository is reviewed and the next milestone is
explicitly selected.

### Latest Verification

- `httpx` is a locked runtime dependency; `pytest` and `ruff` are locked
  development dependencies.
- Client, schema, service, configuration, and API tests: `32 passed`.
- Ruff format check: passed for 28 files.
- Ruff lint check: passed.
- Live SEC access: passed on September 25, 2026, for `AAPL` and `HPE`.
- `AAPL` returned recent 8-K filings dated July 30 and April 30, 2026.
- `HPE` returned recent 8-K filings dated September 2 and August 4, 2026.
- The live check used the ignored local `WATCHTOWER_SEC_USER_AGENT`; its value
  was not printed or committed.
- yfinance `1.7.0` is locked, and the price adapter passed live checks for both
  `AAPL` and `HPE` on September 25, 2026.
- The live price records contained Watchtower-owned daily-close fields in USD;
  no yfinance object or raw response crossed the adapter boundary.
- The Marketaux token is loaded from the ignored `.env`; its value was not
  printed or committed.
- The Marketaux adapter returned three normalized ticker-associated headlines
  each for `AAPL` and `HPE` on September 25, 2026.
- Live results confirmed that ticker association can include broader market
  stories mentioning a company; relevance evaluation remains outside this
  demo milestone.
- Public Pydantic models now define strict filing, daily-price, headline,
  source-metadata, and aggregate company-snapshot response contracts.
- Schema tests verify JSON serialization, timezone-aware timestamps, forbidden
  extra fields, URL validation, and finite positive closing prices.
- The company-snapshot service uses injected typed client contracts and fetches
  Marketaux last so invalid tickers or earlier provider failures do not consume
  a rationed news call.
- Live service composition passed for `AAPL` and `HPE`; each serialized response
  contained five 8-K records, one daily-price record, and three headlines.
- FastAPI `/docs` and `/openapi.json` returned HTTP 200 and documented
  `/companies/{ticker}/snapshot`.
- Live HTTP requests for `AAPL` and `HPE` returned HTTP 200 with five filings,
  one USD price record, and three headlines each.
- Malformed tickers and owned provider failures have API tests for controlled
  422, 404, 502, and 503 behavior without leaking internal messages.
- `httpx2` is a development-only dependency used by Starlette's current test
  client; runtime provider requests continue to use `httpx`.
- `uv.lock` is current, `.venv` is synchronized, and `.env` is ignored.
- The README documents prerequisites, safe environment setup, architecture,
  Swagger usage, AAPL/HPE demo requests, response semantics, errors, quality
  checks, limitations, and deferred scope.
- Swagger now opens the single operation by default under the clearer
  `Company snapshots` tag.
- The README demo workflow passed end to end on port 8001 because an existing
  user-owned Python process was already listening on port 8000; `/docs`, AAPL,
  and HPE returned HTTP 200, and both API responses parsed as valid JSON.

### Acceptance Criteria

- [x] `uv sync` reproduces the locked environment.
- [x] SEC, price, and news providers are isolated in separate client modules.
- [x] Provider payloads are normalized before leaving their client boundaries.
- [x] `GET /companies/AAPL/snapshot` returns schema-valid Watchtower JSON.
- [x] `GET /companies/HPE/snapshot` returns schema-valid Watchtower JSON.
- [x] `/docs` loads and describes the route and owned schemas.
- [x] A provider failure produces a controlled response rather than a traceback
      or leaked provider payload.
- [x] Tests, formatting, and lint checks pass.
- [x] README instructions reproduce the demo locally.
- [x] No secrets, proprietary scoring logic, or private assets appear in Git.

### Explicitly Out of Scope

- Consequence scoring, recommendations, sentiment, ML, LLMs, RAG, embeddings,
  agents, or knowledge graphs.
- PostgreSQL, Redis, background workers, authentication, frontend, cloud
  deployment, and GitHub Actions.
- Scraping or storing full news article bodies.
- More endpoints or fields than the demo requires.

### Existing Verified Foundation

- Python `3.14.6` and `uv 0.12.13`.
- Git repository on `main`, with no commits yet.
- FastAPI `0.141.1`, Pydantic `2.13.5`, and Uvicorn `0.54.0` import successfully.
- `uv.lock` is current and `.venv/` is synchronized and ignored.
- Product, mentoring, and public/private architecture documentation exists.

### Completion Evidence

Milestone 1 closed on September 25, 2026. The documented commands started the
service; AAPL and HPE returned real provider-backed owned schemas; tests and
static checks passed; and the README workflow reproduced the demo.
