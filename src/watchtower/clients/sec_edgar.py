"""SEC EDGAR client with Watchtower-owned normalized records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx


class SecEdgarError(RuntimeError):
    """Base error for failures at the SEC EDGAR provider boundary."""


class SecRequestError(SecEdgarError):
    """Raised when an SEC HTTP request or JSON decode fails."""


class SecPayloadError(SecEdgarError):
    """Raised when an SEC response does not match the expected structure."""


class SecTickerNotFoundError(SecEdgarError):
    """Raised when the SEC ticker mapping does not contain a ticker."""


@dataclass(frozen=True, slots=True)
class SecCompany:
    """A company identity normalized from the SEC ticker mapping."""

    ticker: str
    cik: str
    name: str


@dataclass(frozen=True, slots=True)
class SecFiling:
    """Filing metadata normalized from the SEC submissions response."""

    ticker: str
    cik: str
    company_name: str
    accession_number: str
    form: str
    filing_date: date
    report_date: date | None
    primary_document: str
    primary_document_url: str


class SecEdgarClient:
    """Resolve tickers and retrieve recent 8-K metadata from SEC EDGAR."""

    PROVIDER_NAME = "SEC EDGAR"
    TICKER_MAPPING_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
    ARCHIVES_URL_TEMPLATE = (
        "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
    )

    def __init__(
        self,
        *,
        user_agent: str,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        normalized_user_agent = user_agent.strip()
        if not normalized_user_agent:
            raise ValueError("SEC user agent must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("SEC timeout must be greater than zero")

        # SEC requires an identifying User-Agent. Keep all request policy in
        # this client so callers cannot accidentally omit it.
        self._headers = {
            "User-Agent": normalized_user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        self._timeout = timeout_seconds
        # Tests inject a fake HTTP client; production owns and later closes the
        # real client it creates here.
        self._http = http_client or httpx.Client()
        self._owns_http_client = http_client is None
        # The ticker mapping changes slowly, so cache it for this process and
        # avoid downloading the whole SEC mapping for every ticker request.
        self._companies_by_ticker: dict[str, SecCompany] | None = None

    def close(self) -> None:
        """Close the internally created HTTP client, if this instance owns it."""

        if self._owns_http_client:
            self._http.close()

    def __enter__(self) -> SecEdgarClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def resolve_company(self, ticker: str) -> SecCompany:
        """Resolve a ticker to Watchtower-owned company identity data."""

        normalized_ticker = self._normalize_ticker(ticker)
        companies = self._get_companies_by_ticker()
        try:
            return companies[normalized_ticker]
        except KeyError as exc:
            raise SecTickerNotFoundError(
                f"SEC ticker mapping does not contain {normalized_ticker}"
            ) from exc

    def get_recent_8k_filings(
        self,
        ticker: str,
        *,
        limit: int = 5,
    ) -> list[SecFiling]:
        """Return up to ``limit`` recent 8-K filings for ``ticker``."""

        if limit < 1:
            raise ValueError("SEC filing limit must be at least one")

        # A ticker is for users; the CIK is the SEC's stable identifier used in
        # the submissions endpoint and archive URLs.
        company = self.resolve_company(ticker)
        submissions_url = self.SUBMISSIONS_URL_TEMPLATE.format(cik=company.cik)
        payload = self._get_json(submissions_url)
        recent = self._extract_recent_filings(payload)

        filings: list[SecFiling] = []
        # SEC returns parallel arrays. The same index identifies one filing
        # across form, date, accession, and primary-document fields.
        for index, form in enumerate(recent["form"]):
            if form != "8-K":
                continue

            accession_number = recent["accessionNumber"][index]
            primary_document = recent["primaryDocument"][index]
            filing_date = self._parse_required_date(
                recent["filingDate"][index], field="filingDate"
            )
            report_date = self._parse_optional_date(
                recent["reportDate"][index], field="reportDate"
            )
            # SEC archive folders remove hyphens from the accession number.
            filing_url = self.ARCHIVES_URL_TEMPLATE.format(
                cik=int(company.cik),
                accession=accession_number.replace("-", ""),
                document=primary_document,
            )
            filings.append(
                SecFiling(
                    ticker=company.ticker,
                    cik=company.cik,
                    company_name=company.name,
                    accession_number=accession_number,
                    form=form,
                    filing_date=filing_date,
                    report_date=report_date,
                    primary_document=primary_document,
                    primary_document_url=filing_url,
                )
            )
            if len(filings) == limit:
                break

        return filings

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise ValueError("ticker must not be empty")
        return normalized_ticker

    def _get_companies_by_ticker(self) -> dict[str, SecCompany]:
        if self._companies_by_ticker is not None:
            return self._companies_by_ticker

        payload = self._get_json(self.TICKER_MAPPING_URL)
        if not isinstance(payload, dict):
            raise SecPayloadError("SEC ticker mapping must be a JSON object")

        companies: dict[str, SecCompany] = {}
        # The mapping uses numeric JSON-object keys, so the record values—not
        # their keys—contain the company identity data we need.
        for raw_record in payload.values():
            if not isinstance(raw_record, dict):
                continue

            raw_ticker = raw_record.get("ticker")
            if not isinstance(raw_ticker, str) or not raw_ticker.strip():
                continue

            try:
                cik_number = int(raw_record["cik_str"])
                company_name = str(raw_record["title"]).strip()
            except (KeyError, TypeError, ValueError) as exc:
                raise SecPayloadError(
                    f"SEC ticker record for {raw_ticker.upper()} is malformed"
                ) from exc

            if cik_number <= 0 or not company_name:
                raise SecPayloadError(
                    f"SEC ticker record for {raw_ticker.upper()} is malformed"
                )

            ticker = raw_ticker.strip().upper()
            companies[ticker] = SecCompany(
                ticker=ticker,
                cik=f"{cik_number:010d}",
                name=company_name,
            )

        if not companies:
            raise SecPayloadError("SEC ticker mapping contains no valid companies")

        self._companies_by_ticker = companies
        return companies

    def _get_json(self, url: str) -> Any:
        try:
            response = self._http.get(
                url,
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SecRequestError("SEC request failed") from exc

    @staticmethod
    def _extract_recent_filings(payload: Any) -> dict[str, list[str]]:
        try:
            recent = payload["filings"]["recent"]
        except (KeyError, TypeError) as exc:
            raise SecPayloadError(
                "SEC submissions response is missing recent filings"
            ) from exc

        required_fields = (
            "accessionNumber",
            "filingDate",
            "reportDate",
            "form",
            "primaryDocument",
        )
        arrays: dict[str, list[str]] = {}
        for field in required_fields:
            values = recent.get(field) if isinstance(recent, dict) else None
            if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values
            ):
                raise SecPayloadError(
                    f"SEC recent filings field {field} must be a string array"
                )
            arrays[field] = values

        # Parallel arrays are safe only when every required field has the same
        # length; otherwise indexing could combine data from different filings.
        lengths = {len(values) for values in arrays.values()}
        if len(lengths) != 1:
            raise SecPayloadError("SEC recent filing arrays have inconsistent lengths")

        return arrays

    @staticmethod
    def _parse_required_date(value: str, *, field: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise SecPayloadError(f"SEC {field} value is not an ISO date") from exc

    @classmethod
    def _parse_optional_date(cls, value: str, *, field: str) -> date | None:
        if not value:
            return None
        return cls._parse_required_date(value, field=field)
