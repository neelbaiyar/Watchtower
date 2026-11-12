# Watchtower

Watchtower is a source-grounded technology company research API. Given a ticker,
it combines recent SEC 8-K filings, a daily market-price snapshot, and current
headline metadata into one Watchtower-owned JSON response with a transparent
research-priority signal.

This repository contains a complete FastAPI research dashboard with a durable
local snapshot cache and a local-only Go foundation for SEC 8-K ingestion. It
is a research tool, not an investment recommendation or automated trading
system.

## What Watchtower provides

- Ticker is runtime input; `AAPL`, `NVDA`, and other supported tickers are
  not hardcoded.
- SEC EDGAR, yfinance, and Marketaux are isolated behind separate clients.
- Vendor payloads are normalized before reaching application or HTTP layers.
- A service layer composes the providers while the FastAPI route stays thin.
- Strict Pydantic models define the public JSON and OpenAPI contracts.
- Provider failures become controlled HTTP responses instead of leaked payloads.
- A deterministic, source-linked research-attention signal makes evidence
  visible without claiming to predict price direction.
- A local browser dashboard keeps a small ticker watchlist on the current
  device and presents the signal, source links, and retrieval times clearly.
- Optional local PostgreSQL storage survives application restarts and returns
  an explicitly marked stale snapshot if a live provider is unavailable.
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

When the optional local cache is enabled, the service first checks a fresh
Watchtower-owned snapshot in PostgreSQL. A manual refresh bypasses that cache;
provider responses still travel through the same clients and service before a
replacement snapshot is stored.

## Explainable research-priority signal

Every company snapshot includes `research_signal`. It is a reproducible,
five-level **research-attention** result—not a price forecast or investment
recommendation. Its purpose is to help a user decide what to investigate next.

| Level | Attention-score range | Meaning |
| --- | ---: | --- |
| `quiet` | 0 | No weighted activity in the current snapshot. |
| `low_attention` | 1–24 | Some activity is present. |
| `monitor` | 25–49 | Multiple visible facts justify keeping the company in view. |
| `elevated_attention` | 50–74 | The snapshot contains substantial activity worth timely review. |
| `high_attention` | 75–100 | Several strong activity indicators warrant prioritizing research. |

The public baseline uses only normalized facts already present in a snapshot:

| Evidence | Points |
| --- | ---: |
| Each of the first three recent 8-K filings | 12 each |
| Fourth or later 8-K filing | 4 total extra, capped at 40 filing points |
| Each of the first three ticker-associated headlines | 6 each |
| Daily price-movement magnitude of 0.25%, 1%, 3%, or 5%+ | 8, 18, 30, or 42 |

Price direction is intentionally ignored: an upward or downward move of the
same size receives the same attention weight. Each signal includes its score,
level, a deterministic explanation, and source-linked filing/headline evidence.
The price client currently has no direct source URL, so price evidence names its
provider without inventing a link.

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

## Optional durable local cache

The dashboard works without Docker through live requests. To retain complete
Watchtower snapshots across restarts and use a stored fallback when an upstream
provider is unavailable, enable the local PostgreSQL cache.

1. Add `WATCHTOWER_SNAPSHOT_DATABASE_URL` to the ignored root `.env` using the
   same local database password as `infra/postgres/.env`.
2. Start PostgreSQL:

   ```bash
   docker compose up -d --wait
   ```

3. A new database runs every migration automatically. If your database volume
   already exists, apply the snapshot-table migration once:

   ```bash
   docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
     < infra/postgres/migrations/003_create_company_snapshots.sql
   ```

With the default five-minute TTL, a selected ticker shows a `cached` snapshot
until it expires. **Refresh sources** makes a live request immediately. If that
live request fails and a prior snapshot exists, the dashboard shows it as
`stale`, including its original generation time.

## Run Watchtower

Start the application:

```bash
uv run --env-file .env uvicorn watchtower.main:app --host 127.0.0.1 --port 8000
```

Leave that terminal running. Open the local research dashboard:

<http://127.0.0.1:8000/>

Add a ticker such as `AAPL` or `NVDA`, then select it from the watchlist.
The watchlist stays only in that browser's local storage; it is not sent to or
stored by Watchtower. Watchtower restores the last selected saved ticker at
startup. Without the optional cache, selecting a ticker makes one live snapshot
request, so avoid repeatedly refreshing it when conserving the Marketaux request
budget.
When the optional durable cache is configured, selecting a recently cached
ticker avoids another provider request; use **Refresh sources** for a live
update.

For developer-facing interactive API documentation, open:

<http://127.0.0.1:8000/docs>

Under **Company snapshots**, open **GET /companies/{ticker}/snapshot**, select
**Try it out**, enter a ticker, and select **Execute** to inspect the raw
Watchtower-owned JSON contract.

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
# Optional: point the Python dashboard/API cache at the same local database.
WATCHTOWER_SNAPSHOT_DATABASE_URL="postgres://watchtower:your-local-password@127.0.0.1:5432/watchtower?sslmode=disable"
WATCHTOWER_SNAPSHOT_CACHE_TTL_SECONDS="300"
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
- `snapshot_status`, which is `live`, `cached`, or `stale` so freshness is
  always explicit.
- `filings`, containing SEC source metadata and recent 8-K records.
- `price`, containing its source metadata and latest daily-close information.
- `news`, containing Marketaux retrieval metadata and article metadata.
- `research_signal`, containing a research-attention score, ordered level,
  source-linked evidence, explanation, and an explicit limitation statement.

Source retrieval timestamps are deliberately separate from filing dates,
trading dates, and article publication times. A response retrieved now can
contain an event that happened earlier.

## HTTP behavior

- `200`: snapshot returned successfully.
- `404`: ticker is absent from the SEC ticker mapping.
- `422`: ticker path format is invalid.
- `502`: an upstream provider request failed or returned unusable data.
- `503`: the news provider rejected configuration or reached its rate limit.

Without a stored snapshot, a required provider failure returns a controlled
error instead of a partial snapshot. With the optional cache enabled,
Watchtower returns the last complete validated snapshot as `stale` instead.

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
- PostgreSQL snapshot caching is optional; without its ignored local URL and a
  running Docker database, the FastAPI endpoint remains live-only.
- The Go poller has an explicit one-shot mode, but no recurring scheduler.
- The public signal is a transparent baseline, not a trained ML model, sentiment
  classifier, ranking system, knowledge graph, or consequence engine.
- No private scoring logic, model weights, labeled dataset, or proprietary
  heuristic is present in this repository.

Recurring polling and consumption of EDGAR-triggered refresh requests remain
future work. Proprietary scoring or model logic will remain outside this public
repository and behind a typed boundary when that milestone arrives.
