"""Watchtower-owned response contract for a company snapshot."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl


class WatchtowerResponseModel(BaseModel):
    """Strict, immutable base for public response models."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class SourceMetadata(WatchtowerResponseModel):
    """Identifies a provider and when Watchtower retrieved its data."""

    provider: str = Field(min_length=1)
    retrieved_at: AwareDatetime


class FilingResponse(WatchtowerResponseModel):
    """Public metadata for one SEC 8-K filing."""

    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: Literal["8-K"]
    filing_date: date
    report_date: date | None
    document_url: HttpUrl


class FilingsSectionResponse(WatchtowerResponseModel):
    """SEC filing results and their retrieval provenance."""

    source: SourceMetadata
    items: list[FilingResponse]


class DailyPriceResponse(WatchtowerResponseModel):
    """Latest daily market-price values exposed by Watchtower."""

    price_date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    latest_close: float = Field(gt=0)
    previous_close: float | None = Field(default=None, gt=0)
    change: float | None = None
    change_percent: float | None = None


class PriceSectionResponse(WatchtowerResponseModel):
    """Daily price data and its retrieval provenance."""

    source: SourceMetadata
    data: DailyPriceResponse


class HeadlineResponse(WatchtowerResponseModel):
    """Public metadata for one ticker-associated news article."""

    title: str = Field(min_length=1)
    snippet: str | None
    url: HttpUrl
    published_at: AwareDatetime
    publisher: str = Field(min_length=1)


class NewsSectionResponse(WatchtowerResponseModel):
    """Ticker-associated headlines and their retrieval provenance."""

    source: SourceMetadata
    items: list[HeadlineResponse]


class CompanySnapshotResponse(WatchtowerResponseModel):
    """Stable public contract composed from Watchtower's provider boundaries."""

    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    company_name: str = Field(min_length=1)
    cik: str = Field(pattern=r"^\d{10}$")
    generated_at: AwareDatetime
    filings: FilingsSectionResponse
    price: PriceSectionResponse
    news: NewsSectionResponse
