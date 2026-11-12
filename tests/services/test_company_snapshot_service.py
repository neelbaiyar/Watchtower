"""Service tests with fakes that expose orchestration order and data flow."""

from datetime import UTC, date, datetime, timedelta

import pytest

from watchtower.clients.marketaux import NewsHeadline
from watchtower.clients.sec_edgar import SecCompany, SecFiling
from watchtower.clients.yfinance import DailyPriceSnapshot
from watchtower.schemas import ResearchSignalResponse
from watchtower.services.company_snapshot import CompanySnapshotService
from watchtower.signals import (
    ResearchSignalInput,
    TransparentResearchSignalEngine,
)


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
                        "source_urls": list(signal_input.filing_urls),
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
            filing_provider="SEC EDGAR",
            filing_urls=(
                "https://www.sec.gov/Archives/edgar/data/1645590/"
                "000164559026000078/hpe-20260902.htm",
            ),
            headline_provider="Marketaux",
            headline_urls=("https://example.com/hpe-high",),
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
