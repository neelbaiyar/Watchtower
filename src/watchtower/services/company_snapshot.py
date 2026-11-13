"""Application service for composing a public company snapshot."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import ValidationError

from watchtower.clients.marketaux import NewsClientError, NewsHeadline
from watchtower.clients.sec_edgar import (
    SecCompany,
    SecEdgarError,
    SecFiling,
    SecTickerNotFoundError,
)
from watchtower.clients.yfinance import DailyPriceSnapshot, PriceClientError
from watchtower.schemas.company_snapshot import (
    CompanySnapshotResponse,
    DailyPriceResponse,
    FilingResponse,
    FilingsSectionResponse,
    HeadlineResponse,
    NewsSectionResponse,
    PriceSectionResponse,
    SnapshotStatus,
    SourceMetadata,
)
from watchtower.signals.contracts import (
    FilingFact,
    HeadlineFact,
    ResearchSignalEngine,
    ResearchSignalInput,
)
from watchtower.storage import CachedSnapshot, SnapshotStore, SnapshotStoreError

logger = logging.getLogger(__name__)


class SnapshotCompositionError(RuntimeError):
    """Raised when provider records cannot form a valid public snapshot."""


class SecClient(Protocol):
    # A Protocol describes the methods the service needs, allowing real clients
    # and test fakes to be swapped without changing service code.
    PROVIDER_NAME: str

    def resolve_company(self, ticker: str) -> SecCompany: ...

    def get_recent_8k_filings(
        self,
        ticker: str,
        *,
        limit: int = 5,
    ) -> list[SecFiling]: ...


class PriceClient(Protocol):
    PROVIDER_NAME: str

    def get_daily_price(self, ticker: str) -> DailyPriceSnapshot: ...


class NewsClient(Protocol):
    PROVIDER_NAME: str

    def get_headlines(self, ticker: str, *, limit: int = 3) -> list[NewsHeadline]: ...


class CompanySnapshotService:
    """Coordinate provider clients and construct Watchtower's public response."""

    def __init__(
        self,
        *,
        sec_client: SecClient,
        price_client: PriceClient,
        news_client: NewsClient,
        signal_engine: ResearchSignalEngine,
        snapshot_store: SnapshotStore | None = None,
        snapshot_cache_ttl: timedelta | None = None,
        refresh_cooldown: timedelta | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # Dependencies enter at construction time instead of being created in
        # the method below. That is dependency injection and keeps tests local.
        self._sec_client = sec_client
        self._price_client = price_client
        self._news_client = news_client
        # The service depends on the contract, not the public baseline class.
        # A future implementation can therefore be injected without changing
        # this orchestration code or the HTTP route.
        self._signal_engine = signal_engine
        # A controllable clock makes retrieval timestamps deterministic in tests.
        self._clock = clock or (lambda: datetime.now(UTC))
        # Storage is optional: local live-only development remains useful, but
        # a configured PostgreSQL store makes a successful snapshot durable.
        self._snapshot_store = snapshot_store
        self._snapshot_cache_ttl = snapshot_cache_ttl or timedelta(minutes=5)
        if self._snapshot_cache_ttl <= timedelta():
            raise ValueError("snapshot cache TTL must be greater than zero")
        # Every live snapshot spends one request from a small daily news quota,
        # and `refresh=true` is open to any caller. A stored snapshot younger
        # than this is served instead of honoring another forced refresh.
        self._refresh_cooldown = (
            timedelta(seconds=60) if refresh_cooldown is None else refresh_cooldown
        )
        if self._refresh_cooldown < timedelta():
            raise ValueError("refresh cooldown must not be negative")

    def get_company_snapshot(
        self,
        ticker: str,
        *,
        force_refresh: bool = False,
    ) -> CompanySnapshotResponse:
        """Return a fresh cache entry, live data, or an explicit stale fallback."""

        normalized_ticker = ticker.strip().upper()
        cached = self._load_cached_snapshot(normalized_ticker)
        if cached is not None:
            age = self._now() - cached.cached_at
            # The cooldown is measured from the stored snapshot, not from an
            # in-memory timer, so it survives restarts and needs no extra state.
            bypass_cache = force_refresh and age >= self._refresh_cooldown
            if not bypass_cache and age <= self._snapshot_cache_ttl:
                return self._with_snapshot_status(
                    cached.snapshot, SnapshotStatus.CACHED
                )

        try:
            snapshot = self._build_live_snapshot(ticker)
        # A definitive SEC "not found" result should remain a 404 rather than
        # silently returning an old entry for a symbol that no longer resolves.
        except SecTickerNotFoundError:
            raise
        except (
            SecEdgarError,
            PriceClientError,
            NewsClientError,
            SnapshotCompositionError,
        ):
            if cached is not None:
                return self._with_snapshot_status(cached.snapshot, SnapshotStatus.STALE)
            raise

        self._save_snapshot(snapshot)
        return snapshot

    def _build_live_snapshot(self, ticker: str) -> CompanySnapshotResponse:
        """Build a live company snapshot from normalized provider records."""

        # SEC resolution happens first. A nonexistent ticker fails before we
        # spend a limited news-provider request.
        company = self._sec_client.resolve_company(ticker)
        filings = self._sec_client.get_recent_8k_filings(company.ticker)
        filings_retrieved_at = self._now()

        # Price is cheap context. News stays last because its free-tier request
        # budget is the most constrained of the three sources.
        price = self._price_client.get_daily_price(company.ticker)
        price_retrieved_at = self._now()

        headlines = self._news_client.get_headlines(company.ticker)
        news_retrieved_at = self._now()

        # Clients check structure, but the public schema is stricter (accession
        # format, URL syntax, currency code). A record that passes the client
        # and fails the schema is still a provider problem, so it must reach
        # the stale fallback and the 502 handler rather than surface as a 500.
        try:
            return self._compose_snapshot(
                company=company,
                filings=filings,
                filings_retrieved_at=filings_retrieved_at,
                price=price,
                price_retrieved_at=price_retrieved_at,
                headlines=headlines,
                news_retrieved_at=news_retrieved_at,
            )
        except ValidationError as error:
            raise SnapshotCompositionError(
                "provider data failed public schema validation"
            ) from error

    def _compose_snapshot(
        self,
        *,
        company: SecCompany,
        filings: list[SecFiling],
        filings_retrieved_at: datetime,
        price: DailyPriceSnapshot,
        price_retrieved_at: datetime,
        headlines: list[NewsHeadline],
        news_retrieved_at: datetime,
    ) -> CompanySnapshotResponse:
        # Give the signal engine only Watchtower-normalized facts. Provider JSON
        # and provider-specific parsing remain inside their respective clients.
        # The signal is scored as of the same instant the snapshot reports as
        # its generation time, so a stored snapshot stays self-consistent.
        generated_at = self._now()
        research_signal = self._signal_engine.evaluate(
            ResearchSignalInput(
                as_of=generated_at,
                filing_provider=self._sec_client.PROVIDER_NAME,
                filings=tuple(
                    FilingFact(
                        url=filing.primary_document_url,
                        filing_date=filing.filing_date,
                    )
                    for filing in filings
                ),
                headline_provider=self._news_client.PROVIDER_NAME,
                headlines=tuple(
                    HeadlineFact(url=headline.url, published_at=headline.published_at)
                    for headline in headlines
                ),
                price_provider=self._price_client.PROVIDER_NAME,
                price_change_percent=price.change_percent,
            )
        )

        # This is the application boundary: internal provider records become
        # public Pydantic schema objects with Watchtower-controlled field names.
        return CompanySnapshotResponse(
            ticker=company.ticker,
            company_name=company.name,
            cik=company.cik,
            generated_at=generated_at,
            filings=FilingsSectionResponse(
                source=SourceMetadata(
                    provider=self._sec_client.PROVIDER_NAME,
                    retrieved_at=filings_retrieved_at,
                ),
                items=[self._filing_response(filing) for filing in filings],
            ),
            price=PriceSectionResponse(
                source=SourceMetadata(
                    provider=self._price_client.PROVIDER_NAME,
                    retrieved_at=price_retrieved_at,
                ),
                data=DailyPriceResponse(
                    price_date=price.price_date,
                    currency=price.currency,
                    latest_close=price.latest_close,
                    previous_close=price.previous_close,
                    change=price.change,
                    change_percent=price.change_percent,
                ),
            ),
            news=NewsSectionResponse(
                source=SourceMetadata(
                    provider=self._news_client.PROVIDER_NAME,
                    retrieved_at=news_retrieved_at,
                ),
                items=[self._headline_response(headline) for headline in headlines],
            ),
            research_signal=research_signal,
        )

    def _load_cached_snapshot(self, ticker: str) -> CachedSnapshot | None:
        """Treat an unavailable optional cache as a cache miss, not an API outage."""

        if self._snapshot_store is None:
            return None
        try:
            return self._snapshot_store.load(ticker)
        except SnapshotStoreError as error:
            # Live provider calls remain the source of truth when local storage
            # is temporarily unavailable. The caller receives a provider error
            # only if there is neither live data nor a usable stored snapshot.
            # Log the store's own message only; the driver error underneath can
            # carry connection details.
            logger.warning("snapshot cache read failed for %s: %s", ticker, error)
            return None

    def _save_snapshot(self, snapshot: CompanySnapshotResponse) -> None:
        """Persist a live response without turning a storage hiccup into failure."""

        if self._snapshot_store is None:
            return
        try:
            self._snapshot_store.save(snapshot)
        except SnapshotStoreError as error:
            # The live result is still truthful and useful even if persistence
            # fails. A later successful live request can repair the cache.
            logger.warning(
                "snapshot cache write failed for %s: %s", snapshot.ticker, error
            )
            return

    @staticmethod
    def _with_snapshot_status(
        snapshot: CompanySnapshotResponse,
        status: SnapshotStatus,
    ) -> CompanySnapshotResponse:
        # Pydantic models are frozen, so model_copy is the intentional way to
        # derive a response that states whether its source is cache or live.
        return snapshot.model_copy(update={"snapshot_status": status})

    def _now(self) -> datetime:
        value = self._clock()
        # Naive datetimes are ambiguous across machines and daylight-saving
        # changes, so public retrieval timestamps are normalized to UTC.
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("snapshot clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _filing_response(filing: SecFiling) -> FilingResponse:
        return FilingResponse(
            accession_number=filing.accession_number,
            form=filing.form,
            filing_date=filing.filing_date,
            report_date=filing.report_date,
            document_url=filing.primary_document_url,
        )

    @staticmethod
    def _headline_response(headline: NewsHeadline) -> HeadlineResponse:
        return HeadlineResponse(
            title=headline.title,
            snippet=headline.snippet,
            url=headline.url,
            published_at=headline.published_at,
            publisher=headline.source,
        )
