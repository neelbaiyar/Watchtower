# Watchtower Implementation Decisions

This is a concise operational record for builders and reviewers. Consequential,
long-lived decisions still receive dedicated ADRs.

## 2026-09-25: Real Company Snapshot Slice

- The near-term demo route is `GET /companies/{ticker}/snapshot`; ticker is a
  path input and no provider code is specific to HPE.
- The first aggregate response will compose SEC 8-K metadata, current/recent
  price information, and free headline metadata.
- Provider clients normalize external payloads into Watchtower-owned internal
  records. Public Pydantic schemas belong to Watchtower and are created separately
  from provider response models.
- FastAPI routes remain thin; the company snapshot service owns orchestration.
- External providers remain replaceable behind client modules.
- Provider failures are translated into Watchtower errors and never leak raw
  payloads to API consumers.
- SEC access uses the public submissions API and ticker mapping. A declared
  User-Agent is required through `WATCHTOWER_SEC_USER_AGENT`; no contact address
  is committed.
- Provider clients are synchronous for this small demo. FastAPI will use
  synchronous route execution; async conversion is deferred until measured
  concurrency or latency justifies it.
- The public/private consequence-engine ADR remains active, but no scoring
  interface or private implementation is added in this milestone.

## 2026-09-25: SEC EDGAR Client Increment

- Added a synchronous `httpx` SEC client with injected transport support.
- The client resolves tickers through the SEC mapping, zero-pads CIKs, retrieves
  current submissions, filters exact `8-K` forms, and constructs filing-document
  URLs.
- Provider responses are normalized into frozen Watchtower dataclasses.
- Owned errors cover unknown tickers, HTTP/JSON failures, and malformed provider
  structures without leaking response bodies.
- The ticker mapping is cached per client instance to avoid redundant requests.
- Verification: 5 focused tests pass; Ruff format and lint checks pass.
- The ignored root `.env` supplies `WATCHTOWER_SEC_USER_AGENT` through `uv run
  --env-file .env`; no dotenv runtime dependency was added solely for the smoke
  check.
- Live requests succeeded for both `AAPL` and `HPE` on September 25, 2026.
  Each ticker returned two normalized recent 8-K records with SEC archive links.
- The user-agent value and raw SEC payloads were not printed or recorded.
- The SEC increment is complete. The next provider boundary is the yfinance
  price adapter.

## 2026-09-25: yfinance Price Client Increment

- yfinance `1.7.0` is locked behind `YFinanceClient`; no application code needs
  to depend directly on yfinance or pandas objects.
- `DailyPriceSnapshot` owns ticker, currency, trading date, latest close,
  previous close, absolute change, and percentage change.
- The adapter uses five days of unadjusted daily history. The result is named a
  daily price snapshot rather than a real-time quote so the contract does not
  overstate freshness.
- Provider construction is injectable for focused tests. Owned errors distinguish
  missing history, malformed provider data, and request failures.
- The first live check revealed that yfinance returns `HistoryMetadata`, which
  satisfies `collections.abc.Mapping` but is not a concrete `dict`. Validation
  now targets the mapping interface, and a regression test covers that behavior.
- Verification: 8 total tests pass; Ruff format and lint checks pass; live
  adapter calls succeeded for `AAPL` and `HPE` on September 25, 2026.
- The next provider boundary is free news/headline metadata.

## 2026-09-25: Marketaux News Client Increment

- Marketaux was selected over NewsAPI for the demo because its current free
  plan provides 100 requests per day, three articles per request, instant news
  access, full metadata, and symbol filtering. The API token remains in the
  ignored root `.env` as `WATCHTOWER_MARKETAUX_API_TOKEN`.
- `MarketauxClient` uses the existing synchronous `httpx` dependency and
  normalizes provider articles into `NewsHeadline` records containing ticker,
  title, snippet, URL, publication time, and source.
- Owned errors distinguish rejected credentials, rate exhaustion, request
  failure, and malformed payloads without exposing the token or raw response.
- Empty article results are valid rather than treated as an unsupported ticker.
- Verification: 15 total tests pass; Ruff format and lint checks pass; two live
  calls returned three normalized headlines each for `AAPL` and `HPE`.
- Live results show that symbol-associated results can include broader market
  stories mentioning the company. Relevance scoring or filtering requires
  evaluation and is not part of the current demo.
- Post-Tuesday direction: refresh news unevenly across the day and reserve calls
  for new, deduplicated EDGAR events; no polling or cache is implemented now.
- The next increment is the public Watchtower Pydantic response schemas.

## 2026-09-25: Public Company Snapshot Schemas

- Public response models live in `watchtower.schemas` and remain separate from
  provider dataclasses and vendor payloads.
- The aggregate response groups filings, price data, and news into explicit
  sections. Each section includes provider identity and a timezone-aware
  retrieval timestamp.
- Source-event time remains distinct: filings expose filing/report dates,
  prices expose a trading date, and headlines expose publication time.
- Models are frozen, reject unknown fields, strip surrounding string whitespace,
  reject non-finite numbers, and validate URLs and identifying formats.
- `HeadlineResponse.publisher` is distinct from section-level provider metadata:
  Marketaux is the provider while the publisher is the originating news outlet.
- No recommendation, score, sentiment, or speculative interpretation field is
  part of the contract.
- Verification: 22 total tests pass; Ruff format and lint checks pass.
- The next increment is the company-snapshot service that maps the three client
  outputs into this contract.

## 2026-09-25: Company Snapshot Service

- `CompanySnapshotService` is the application orchestration boundary. It depends
  on small typed client protocols and has no knowledge of HTTP requests, vendor
  JSON, environment variables, or FastAPI.
- SEC company resolution runs first so an invalid ticker fails before other
  calls. Marketaux runs last so earlier failures do not consume a rationed news
  request.
- The service is intentionally all-or-nothing for the demo. Partial-provider
  responses require an explicit public contract and are deferred.
- Provider names are declared by adapters and carried into public source
  metadata without exposing provider response structures.
- An injected clock makes retrieval and generation timestamps deterministic in
  tests. Naive datetimes are rejected, and all accepted times are normalized to
  UTC.
- The first test run found duplicate pytest module basenames in different
  non-package directories. The service test received a unique filename rather
  than introducing global test-import configuration.
- Verification: 24 total tests pass; Ruff format and lint checks pass; live
  service composition succeeded for `AAPL` and `HPE` with five filings, one
  price record, and three headlines each.
- The next increment is the thin FastAPI application, dependency construction,
  and controlled HTTP error translation.

## 2026-09-25: FastAPI Application Boundary

- Runtime settings fail fast during application startup when either required
  environment variable is absent. Setting values are excluded from object
  representations, and error messages contain variable names rather than values.
- The FastAPI lifespan owns long-lived SEC and Marketaux clients and closes them
  during application shutdown. Tests may inject a fake service without loading
  environment configuration or making network calls.
- `GET /companies/{ticker}/snapshot` validates the ticker path, calls the service
  once, and declares `CompanySnapshotResponse` as its response model.
- Central exception handlers keep the route thin: unknown SEC tickers become
  404; malformed path inputs become FastAPI 422 responses; ordinary provider
  failures become 502; news authentication and rate exhaustion become 503.
- API responses use stable Watchtower messages and do not expose provider error
  text, tokens, or personal configuration.
- Starlette `1.7.0` warned that its test client is migrating from `httpx` to
  `httpx2`. The recommended `httpx2` package was added only to the development
  group; production provider clients remain on `httpx`.
- Verification: 32 tests pass with no warnings; Ruff format and lint checks pass;
  `/docs`, OpenAPI, AAPL, and HPE returned HTTP 200 through a real local Uvicorn
  process; shutdown completed cleanly.
- `uv lock --check` and `uv sync --check` pass, and the root `.env` remains
  ignored.
- The final milestone increment is a README that reproduces the verified setup,
  run, query, and quality-check workflow.

## 2026-09-25: Reproducible Demo and Milestone Closure

- The root README is the operator runbook for prerequisites, locked dependency
  setup, safe environment configuration, server startup, Swagger interaction,
  AAPL/HPE requests, response semantics, errors, quality checks, and limitations.
- `.env.example` contains only placeholders. The real `.env` remains ignored and
  the README includes a non-disclosing ignore check.
- Swagger uses the human-readable `Company snapshots` tag, expands the operation
  by default, and documents the endpoint purpose and controlled error statuses.
- Verification: the exact documented quality commands pass with 32 tests; the
  documented server command starts successfully when its port is available; and
  `/docs`, AAPL, and HPE returned HTTP 200 with valid JSON.
- Port 8000 was occupied by a user-owned Python process during final verification,
  so the isolated final run used port 8001 and did not terminate the user's
  process.
- Milestone 1 is complete. Publication is a separate Git checkpoint; no remote
  repository, commit, or push is created implicitly.
