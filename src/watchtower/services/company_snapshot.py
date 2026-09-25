"""Application service for composing a public company snapshot."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from watchtower.clients.marketaux import NewsHeadline
from watchtower.clients.sec_edgar import SecCompany, SecFiling
from watchtower.clients.yfinance import DailyPriceSnapshot
from watchtower.schemas.company_snapshot import (
    CompanySnapshotResponse,
    DailyPriceResponse,
    FilingResponse,
    FilingsSectionResponse,
    HeadlineResponse,
    NewsSectionResponse,
    PriceSectionResponse,
    SourceMetadata,
)


class SecClient(Protocol):
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
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sec_client = sec_client
        self._price_client = price_client
        self._news_client = news_client
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_company_snapshot(self, ticker: str) -> CompanySnapshotResponse:
        """Build a company snapshot from normalized provider records."""

        company = self._sec_client.resolve_company(ticker)
        filings = self._sec_client.get_recent_8k_filings(company.ticker)
        filings_retrieved_at = self._now()

        price = self._price_client.get_daily_price(company.ticker)
        price_retrieved_at = self._now()

        headlines = self._news_client.get_headlines(company.ticker)
        news_retrieved_at = self._now()

        return CompanySnapshotResponse(
            ticker=company.ticker,
            company_name=company.name,
            cik=company.cik,
            generated_at=self._now(),
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
        )

    def _now(self) -> datetime:
        value = self._clock()
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
