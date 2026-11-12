# Watchtower

Watchtower is a source-grounded technology company research API. Given a ticker,
it combines recent SEC 8-K filings, a daily market-price snapshot, and current
headline metadata into one Watchtower-owned JSON response.

This repository contains a complete FastAPI research-snapshot slice and a
local-only Go foundation for durable SEC 8-K ingestion. It is a research tool,
not an investment recommendation or automated trading system.

## What the demo proves

- Ticker is runtime input; `AAPL`, `NVDA`, and other supported tickers are
  not hardcoded.
- SEC EDGAR, yfinance, and Marketaux are isolated behind separate clients.
- Vendor payloads are normalized before reaching application or HTTP layers.
- A service layer composes the providers while the FastAPI route stays thin.
- Strict Pydantic models define the public JSON and OpenAPI contracts.
- Provider failures become controlled HTTP responses instead of leaked payloads.
- Secrets and personal contact configuration remain outside Git.

## Architecture

```text
GET /companies/{ticker}/snapshot
        |
        v
CompanySnapshotService
        |
        +-- SEC EDGAR client  -> recent 8-K metadata
        +-- yfinance client   -> latest and previous daily close
        +-- Marketaux client  -> ticker-associated headlines
        |
        v
CompanySnapshotResponse
```

Provider clients return Watchtower-owned internal records. The service maps
those records into public Pydantic response models; the route never processes
raw vendor JSON.

## Prerequisites

- Python 3.14
- [`uv`](https://docs.astral.sh/uv/)
- Go 1.27 or later, for the optional local poller
- Docker Desktop, for the optional local PostgreSQL database
- A free [Marketaux](https://www.marketaux.com/) API token
- A monitored email address for the SEC-declared `User-Agent`

## Local setup

From the repository root—the directory containing `pyproject.toml`—install the
locked dependencies:

```bash
uv sync
```

For a first-time setup, copy the environment template:

```bash
cp .env.example .env
```

If `.env` already exists, do not overwrite it. Edit it so both values are real:

```text
WATCHTOWER_SEC_USER_AGENT="Watchtower local demo Your Name your-email@example.com"
WATCHTOWER_MARKETAUX_API_TOKEN="your-marketaux-token"
```

The SEC value is an identifying header, not an API key, but it contains personal
contact information. Marketaux's value is a credential. The `.env` file is
ignored by Git; `.env.example` contains placeholders and is safe to commit.

Verify the local file is ignored without displaying its contents:

```bash
git check-ignore -v .env
```

## Run Watchtower

Start the application:

```bash
uv run --env-file .env uvicorn watchtower.main:app --host 127.0.0.1 --port 8000
```

Leave that terminal running. Open the interactive documentation:

<http://127.0.0.1:8000/docs>

Under **Company snapshots**, open **GET /companies/{ticker}/snapshot**, select
**Try it out**, enter a ticker, and select **Execute**.

Suggested demo sequence:

1. Query `AAPL` or `NVDA` to demonstrate general ticker input.
2. Query a second supported ticker of your choice.
3. Point out each provider name and retrieval timestamp in the response.
4. Open a returned SEC filing or news URL to demonstrate provenance.

You can also query the API from another terminal:

```bash
curl --fail --silent http://127.0.0.1:8000/companies/AAPL/snapshot \
  | python -m json.tool

curl --fail --silent http://127.0.0.1:8000/companies/NVDA/snapshot \
  | python -m json.tool
```

Each live request currently calls the three providers. In particular, it spends
one Marketaux request, so avoid repeatedly refreshing `/docs` examples without a
reason.

Stop the server with `Control-C`.

## Optional local Go poller

The Go poller is local-only. Its explicit `--once` mode retrieves recent 8-Ks
for configured SEC CIKs, records the first result as a baseline, and persists
later unseen filings with one refresh request each. It does not run a recurring
schedule yet.

First create the ignored local PostgreSQL configuration:

```bash
cp infra/postgres/.env.example infra/postgres/.env
docker compose up -d
```

Set these values in the root `.env` file. The database password in its URL must
match the one in `infra/postgres/.env`. A CIK is the SEC's ten-digit permanent
company identifier; it is not a ticker.

```text
WATCHTOWER_POLLER_DATABASE_URL="postgres://watchtower:your-local-password@127.0.0.1:5432/watchtower?sslmode=disable"
WATCHTOWER_POLLER_CIKS="your-ten-digit-cik,your-second-ten-digit-cik"
```

Then run one bounded pass:

```bash
cd poller
set -a
source ../.env
set +a
go run ./cmd/poller --once
```

Without `--once`, the command starts and waits for `Control-C`; it makes no
SEC or database request.

## Response structure

The response contains:

- `ticker`, `company_name`, and zero-padded SEC `cik` identity fields.
- `generated_at`, when Watchtower finished assembling the response.
- `filings`, containing SEC source metadata and recent 8-K records.
- `price`, containing its source metadata and latest daily-close information.
- `news`, containing Marketaux retrieval metadata and article metadata.

Source retrieval timestamps are deliberately separate from filing dates,
trading dates, and article publication times. A response retrieved now can
contain an event that happened earlier.

## HTTP behavior

- `200`: snapshot returned successfully.
- `404`: ticker is absent from the SEC ticker mapping.
- `422`: ticker path format is invalid.
- `502`: an upstream provider request failed or returned unusable data.
- `503`: the news provider rejected configuration or reached its rate limit.

The current demo is intentionally all-or-nothing: if a required provider fails,
Watchtower returns a controlled error instead of a partial snapshot.

## Quality checks

Run all checks from the repository root:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

## Current scope and limitations

- Headlines are metadata and links only; Watchtower does not scrape article
  bodies.
- Ticker association does not guarantee that every headline is exclusively
  about that company.
- yfinance is an unofficial Yahoo Finance wrapper and can throttle or change.
- Marketaux's free plan is rate-limited.
- The FastAPI snapshot endpoint performs live provider calls and has no cache.
- The Go poller has an explicit one-shot mode, but no recurring scheduler.
- No ML model, sentiment score, ranking, knowledge graph, or consequence engine
  is part of this milestone.

Recurring polling, cache-backed reads, and consumption of EDGAR-triggered
refresh requests are future work. Proprietary scoring or model logic will
remain outside this public repository and behind a typed boundary when that
milestone arrives.
