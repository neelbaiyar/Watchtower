"""Service tests with fakes that expose orchestration order and data flow."""

from datetime import UTC, date, datetime, timedelta

import pytest

from watchtower.clients.marketaux import NewsHeadline
from watchtower.clients.sec_edgar import SecCompany, SecFiling
from watchtower.clients.yfinance import DailyPriceSnapshot
from watchtower.services.company_snapshot import CompanySnapshotService


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
) -> tuple[CompanySnapshotService, FakeSecClient, FakePriceClient, FakeNewsClient]:
    # One helper creates a complete service plus the fakes needed to inspect
    # which ticker each provider received.
    sec_client = FakeSecClient()
    price_client = FakePriceClient()
    news_client = FakeNewsClient()
    service = CompanySnapshotService(
        sec_client=sec_client,
        price_client=price_client,
        news_client=news_client,
        clock=clock,
    )
    return service, sec_client, price_client, news_client


def test_service_composes_clients_into_public_snapshot() -> None:
    clock = SequenceClock(datetime(2026, 9, 25, 16, 0, tzinfo=UTC))
    service, sec_client, price_client, news_client = build_service(clock=clock)

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
    service, _, _, _ = build_service(clock=SequenceClock(datetime(2026, 9, 25, 16, 0)))

    with pytest.raises(ValueError, match="timezone-aware"):
        service.get_company_snapshot("HPE")
