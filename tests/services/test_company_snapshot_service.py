"""Service tests with fakes that expose orchestration order and data flow."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from watchtower.clients.marketaux import NewsHeadline
from watchtower.clients.sec_edgar import (
    SecCompany,
    SecFiling,
    SecTickerNotFoundError,
)
from watchtower.clients.yfinance import DailyPriceSnapshot, PriceRequestError
from watchtower.schemas import ResearchSignalResponse
from watchtower.services.company_snapshot import (
    CompanySnapshotService,
    SnapshotCompositionError,
)
from watchtower.signals import (
    FilingFact,
    HeadlineFact,
    ResearchSignalInput,
    TransparentResearchSignalEngine,
)
from watchtower.storage import CachedSnapshot, SnapshotStoreError


class FakeSecClient:
    # These fakes match the service Protocols, so this test verifies the real
    # coordination code while avoiding SEC, Yahoo, and news-provider requests.
    PROVIDER_NAME = "SEC EDGAR"

    def __init__(self) -> None:
        self.requested_tickers: list[str] = []

    def resolve_company(self, ticker: str) -> SecCompany:
        self.requested_tickers.append(ticker)
        return SecCompany(
            ticker="HPE",
            cik="0001645590",
            name="Hewlett Packard Enterprise Co",
        )

    def get_recent_8k_filings(
        self,
        ticker: str,
        *,
        limit: int = 5,
    ) -> list[SecFiling]:
        self.requested_tickers.append(ticker)
        assert limit == 5
        return [
            SecFiling(
                ticker="HPE",
                cik="0001645590",
                company_name="Hewlett Packard Enterprise Co",
                accession_number="0001645590-26-000078",
                form="8-K",
                filing_date=date(2026, 9, 2),
                report_date=date(2026, 8, 28),
                primary_document="hpe-20260902.htm",
                primary_document_url=(
                    "https://www.sec.gov/Archives/edgar/data/1645590/"
                    "000164559026000078/hpe-20260902.htm"
                ),
            )
        ]


class FakePriceClient:
    PROVIDER_NAME = "Yahoo Finance via yfinance"

    def __init__(self) -> None:
        self.requested_tickers: list[str] = []

    def get_daily_price(self, ticker: str) -> DailyPriceSnapshot:
        self.requested_tickers.append(ticker)
        return DailyPriceSnapshot(
            ticker="HPE",
            currency="USD",
            price_date=date(2026, 9, 25),
            latest_close=63.73,
            previous_close=63.52,
            change=0.21,
            change_percent=0.3306,
        )


class FakeNewsClient:
    PROVIDER_NAME = "Marketaux"

    def __init__(self) -> None:
        self.requested_tickers: list[str] = []

    def get_headlines(
        self,
        ticker: str,
        *,
        limit: int = 3,
    ) -> list[NewsHeadline]:
        self.requested_tickers.append(ticker)
        assert limit == 3
        return [
            NewsHeadline(
                ticker="HPE",
                title="HPE reaches a 52-week high",
                snippet="The shares reached a new high.",
                url="https://example.com/hpe-high",
                published_at=datetime(2026, 9, 25, 12, 15, 18, tzinfo=UTC),
                source="Example News",
            )
        ]


class FakeSignalEngine:
    """Records normalized inputs instead of reproducing scoring-rule tests."""

    def __init__(self) -> None:
        self.inputs: list[ResearchSignalInput] = []

    def evaluate(self, signal_input: ResearchSignalInput) -> ResearchSignalResponse:
        self.inputs.append(signal_input)
        return ResearchSignalResponse.model_validate(
            {
                "level": "low_attention",
                "attention_score": 12,
                "explanation": "Low research attention from one 8-K filing.",
                "evidence": [
                    {
                        "category": "filing_activity",
                        "source_provider": "SEC EDGAR",
                        "source_urls": [filing.url for filing in signal_input.filings],
                        "points": 12,
                        "summary": "Snapshot contains one recent 8-K filing.",
                    }
                ],
                "limitation": (
                    "Research-priority signal only; not investment advice or a "
                    "price prediction."
                ),
            }
        )


class SequenceClock:
    # Advancing one second per call makes every retrieval timestamp predictable
    # and proves the service records provenance separately for each source.
    def __init__(self, start: datetime) -> None:
        self._next = start

    def __call__(self) -> datetime:
        current = self._next
        self._next += timedelta(seconds=1)
        return current


class FakeSnapshotStore:
    """Small in-memory store used to prove service cache policy without SQL."""

    def __init__(self, cached: CachedSnapshot | None = None) -> None:
        self.cached = cached
        self.loaded_tickers: list[str] = []
        self.saved_snapshots: list[object] = []

    def load(self, ticker: str) -> CachedSnapshot | None:
        self.loaded_tickers.append(ticker)
        return self.cached

    def save(self, snapshot: object) -> None:
        self.saved_snapshots.append(snapshot)


class BrokenSnapshotStore:
    """Simulates a cache whose database is unreachable."""

    def load(self, ticker: str) -> CachedSnapshot | None:
        raise SnapshotStoreError("load cached snapshot")

    def save(self, snapshot: object) -> None:
        raise SnapshotStoreError("save cached snapshot")


class FailingPriceClient:
    """Simulates a transient provider failure after the SEC lookup succeeds."""

    PROVIDER_NAME = "Yahoo Finance via yfinance"

    def get_daily_price(self, ticker: str) -> DailyPriceSnapshot:
        raise PriceRequestError(f"price provider unavailable for {ticker}")


class MalformedAccessionSecClient(FakeSecClient):
    """Returns a filing the SEC client accepts but the public schema rejects."""

    def get_recent_8k_filings(
        self,
        ticker: str,
        *,
        limit: int = 5,
    ) -> list[SecFiling]:
        (filing,) = super().get_recent_8k_filings(ticker, limit=limit)
        return [replace(filing, accession_number="not-an-accession")]


def build_service(
    *,
    clock: SequenceClock | None = None,
) -> tuple[
    CompanySnapshotService,
    FakeSecClient,
    FakePriceClient,
    FakeNewsClient,
    FakeSignalEngine,
]:
    # One helper creates a complete service plus the fakes needed to inspect
    # which ticker each provider received.
    sec_client = FakeSecClient()
    price_client = FakePriceClient()
    news_client = FakeNewsClient()
    signal_engine = FakeSignalEngine()
    service = CompanySnapshotService(
        sec_client=sec_client,
        price_client=price_client,
        news_client=news_client,
        signal_engine=signal_engine,
        clock=clock,
    )
    return service, sec_client, price_client, news_client, signal_engine


def test_service_composes_clients_into_public_snapshot() -> None:
    clock = SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC))
    service, sec_client, price_client, news_client, signal_engine = build_service(
        clock=clock
    )

    snapshot = service.get_company_snapshot(" hpe ")

    # SEC receives the original input to resolve it, then all later provider
    # calls use its normalized ticker identity.
    assert sec_client.requested_tickers == [" hpe ", "HPE"]
    assert price_client.requested_tickers == ["HPE"]
    assert news_client.requested_tickers == ["HPE"]
    assert snapshot.ticker == "HPE"
    assert snapshot.company_name == "Hewlett Packard Enterprise Co"
    assert snapshot.filings.items[0].form == "8-K"
    assert snapshot.price.data.latest_close == 63.73
    assert snapshot.news.items[0].publisher == "Example News"
    assert snapshot.research_signal.level == "low_attention"
    assert signal_engine.inputs == [
        ResearchSignalInput(
            as_of=snapshot.generated_at,
            filing_provider="SEC EDGAR",
            filings=(
                FilingFact(
                    url=(
                        "https://www.sec.gov/Archives/edgar/data/1645590/"
                        "000164559026000078/hpe-20260902.htm"
                    ),
                    filing_date=date(2026, 9, 2),
                ),
            ),
            headline_provider="Marketaux",
            headlines=(
                HeadlineFact(
                    url="https://example.com/hpe-high",
                    published_at=datetime(2026, 9, 25, 12, 15, 18, tzinfo=UTC),
                ),
            ),
            price_provider="Yahoo Finance via yfinance",
            price_change_percent=0.3306,
        )
    ]
    assert snapshot.filings.source.retrieved_at == datetime(
        2026, 9, 25, 16, 0, tzinfo=UTC
    )
    assert snapshot.price.source.retrieved_at == datetime(
        2026, 9, 25, 16, 0, 1, tzinfo=UTC
    )
    assert snapshot.news.source.retrieved_at == datetime(
        2026, 9, 25, 16, 0, 2, tzinfo=UTC
    )
    assert snapshot.generated_at == datetime(2026, 9, 25, 16, 0, 3, tzinfo=UTC)


def test_service_rejects_a_naive_clock() -> None:
    service, _, _, _, _ = build_service(
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0))
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        service.get_company_snapshot("HPE")


def test_service_can_use_the_public_transparent_signal_baseline() -> None:
    sec_client = FakeSecClient()
    price_client = FakePriceClient()
    news_client = FakeNewsClient()
    service = CompanySnapshotService(
        sec_client=sec_client,
        price_client=price_client,
        news_client=news_client,
        signal_engine=TransparentResearchSignalEngine(),
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    snapshot = service.get_company_snapshot("HPE")

    # One filing (12), one headline (6), and a 0.33% movement (8) create a
    # reproducible monitor-level attention result without inferring direction.
    assert snapshot.research_signal.attention_score == 26
    assert snapshot.research_signal.level == "monitor"
    assert [item.category for item in snapshot.research_signal.evidence] == [
        "filing_activity",
        "headline_activity",
        "price_movement",
    ]


def test_service_persists_a_successful_live_snapshot() -> None:
    store = FakeSnapshotStore()
    sec_client = FakeSecClient()
    service = CompanySnapshotService(
        sec_client=sec_client,
        price_client=FakePriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=store,
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    snapshot = service.get_company_snapshot("HPE")

    assert snapshot.snapshot_status == "live"
    assert store.loaded_tickers == ["HPE"]
    assert store.saved_snapshots == [snapshot]


def test_service_uses_fresh_cached_snapshot_without_calling_providers() -> None:
    live_service, _, _, _, _ = build_service(
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC))
    )
    cached_snapshot = live_service.get_company_snapshot("HPE")
    store = FakeSnapshotStore(
        CachedSnapshot(
            snapshot=cached_snapshot,
            cached_at=datetime(2026, 9, 25, 16, 1, tzinfo=UTC),
        )
    )
    sec_client = FakeSecClient()
    service = CompanySnapshotService(
        sec_client=sec_client,
        price_client=FailingPriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=store,
        clock=SequenceClock(datetime(2026, 9, 25, 16, 2, tzinfo=UTC)),
    )

    snapshot = service.get_company_snapshot("HPE")

    assert snapshot.snapshot_status == "cached"
    assert sec_client.requested_tickers == []


def test_service_returns_stale_snapshot_after_forced_refresh_provider_failure() -> None:
    live_service, _, _, _, _ = build_service(
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC))
    )
    cached_snapshot = live_service.get_company_snapshot("HPE")
    store = FakeSnapshotStore(
        CachedSnapshot(
            snapshot=cached_snapshot,
            cached_at=datetime(2026, 9, 25, 15, 0, tzinfo=UTC),
        )
    )
    sec_client = FakeSecClient()
    service = CompanySnapshotService(
        sec_client=sec_client,
        price_client=FailingPriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=store,
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    snapshot = service.get_company_snapshot("HPE", force_refresh=True)

    assert snapshot.snapshot_status == "stale"
    assert sec_client.requested_tickers == ["HPE", "HPE"]


def test_schema_invalid_provider_data_raises_an_owned_error() -> None:
    service = CompanySnapshotService(
        sec_client=MalformedAccessionSecClient(),
        price_client=FakePriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    with pytest.raises(SnapshotCompositionError) as error:
        service.get_company_snapshot("HPE")

    assert "not-an-accession" not in str(error.value)


def test_schema_invalid_provider_data_falls_back_to_stale_snapshot() -> None:
    live_service, _, _, _, _ = build_service(
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC))
    )
    store = FakeSnapshotStore(
        CachedSnapshot(
            snapshot=live_service.get_company_snapshot("HPE"),
            cached_at=datetime(2026, 9, 25, 15, 0, tzinfo=UTC),
        )
    )
    service = CompanySnapshotService(
        sec_client=MalformedAccessionSecClient(),
        price_client=FakePriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=store,
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    snapshot = service.get_company_snapshot("HPE")

    assert snapshot.snapshot_status == "stale"
    assert store.saved_snapshots == []


def test_unavailable_cache_is_logged_and_does_not_block_a_live_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = CompanySnapshotService(
        sec_client=FakeSecClient(),
        price_client=FakePriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=BrokenSnapshotStore(),
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    with caplog.at_level("WARNING", logger="watchtower.services.company_snapshot"):
        snapshot = service.get_company_snapshot("HPE")

    assert snapshot.snapshot_status == "live"
    assert [record.getMessage() for record in caplog.records] == [
        "snapshot cache read failed for HPE: load cached snapshot",
        "snapshot cache write failed for HPE: save cached snapshot",
    ]


def _cached_hpe_snapshot(cached_at: datetime) -> CachedSnapshot:
    live_service, _, _, _, _ = build_service(
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC))
    )
    return CachedSnapshot(
        snapshot=live_service.get_company_snapshot("HPE"),
        cached_at=cached_at,
    )


def test_expired_cache_entry_is_replaced_by_a_live_snapshot() -> None:
    store = FakeSnapshotStore(
        _cached_hpe_snapshot(datetime(2026, 9, 25, 15, 0, tzinfo=UTC))
    )
    sec_client = FakeSecClient()
    service = CompanySnapshotService(
        sec_client=sec_client,
        price_client=FakePriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=store,
        snapshot_cache_ttl=timedelta(minutes=5),
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    snapshot = service.get_company_snapshot("HPE")

    assert snapshot.snapshot_status == "live"
    assert sec_client.requested_tickers == ["HPE", "HPE"]
    assert store.saved_snapshots == [snapshot]


def test_unknown_ticker_is_not_masked_by_a_stored_snapshot() -> None:
    class UnknownTickerSecClient(FakeSecClient):
        def resolve_company(self, ticker: str) -> SecCompany:
            raise SecTickerNotFoundError(f"no mapping for {ticker}")

    store = FakeSnapshotStore(
        _cached_hpe_snapshot(datetime(2026, 9, 25, 15, 0, tzinfo=UTC))
    )
    service = CompanySnapshotService(
        sec_client=UnknownTickerSecClient(),
        price_client=FakePriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=store,
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    with pytest.raises(SecTickerNotFoundError):
        service.get_company_snapshot("HPE")


def test_provider_failure_without_a_stored_snapshot_is_raised() -> None:
    service = CompanySnapshotService(
        sec_client=FakeSecClient(),
        price_client=FailingPriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=FakeSignalEngine(),
        snapshot_store=FakeSnapshotStore(),
        clock=SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC)),
    )

    with pytest.raises(PriceRequestError):
        service.get_company_snapshot("HPE")


def test_old_filings_and_headlines_do_not_raise_the_public_signal() -> None:
    # The fakes return a September 2026 filing and headline. Months later the
    # providers would still return them as their newest items.
    service = CompanySnapshotService(
        sec_client=FakeSecClient(),
        price_client=FakePriceClient(),
        news_client=FakeNewsClient(),
        signal_engine=TransparentResearchSignalEngine(),
        clock=SequenceClock(datetime(2027, 3, 1, 16, 0, tzinfo=UTC)),
    )

    snapshot = service.get_company_snapshot("HPE")

    assert len(snapshot.filings.items) == 1
    assert len(snapshot.news.items) == 1
    assert [item.category for item in snapshot.research_signal.evidence] == [
        "price_movement"
    ]
    assert snapshot.research_signal.level == "low_attention"
