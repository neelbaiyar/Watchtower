"""yfinance adapter with Watchtower-owned normalized price records."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

import yfinance as yf


class PriceClientError(RuntimeError):
    """Base error for failures at the market-price provider boundary."""


class PriceRequestError(PriceClientError):
    """Raised when yfinance cannot complete a provider request."""


class PriceNotFoundError(PriceClientError):
    """Raised when no price history exists for a ticker."""


class PricePayloadError(PriceClientError):
    """Raised when yfinance returns an unusable response shape."""


@dataclass(frozen=True, slots=True)
class DailyPriceSnapshot:
    """A Watchtower-owned summary of the latest daily market price."""

    ticker: str
    currency: str
    price_date: date
    latest_close: float
    previous_close: float | None
    change: float | None
    change_percent: float | None


class _Ticker(Protocol):
    # This narrow protocol is the seam used by tests; they need only the two
    # yfinance operations this adapter actually calls.
    def history(self, **kwargs: object) -> Any: ...

    def get_history_metadata(self) -> Any: ...


class YFinanceClient:
    """Retrieve daily prices without exposing yfinance objects to Watchtower."""

    PROVIDER_NAME = "Yahoo Finance via yfinance"

    def __init__(
        self,
        *,
        ticker_factory: Callable[[str], _Ticker] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("price timeout must be greater than zero")

        # Production uses yfinance; tests can provide a small pretend ticker to
        # verify parsing and price calculations without the network.
        self._ticker_factory = ticker_factory or yf.Ticker
        self._timeout = timeout_seconds

    def get_daily_price(self, ticker: str) -> DailyPriceSnapshot:
        """Return the latest and previous daily closes for ``ticker``."""

        normalized_ticker = self._normalize_ticker(ticker)
        provider_ticker = self._ticker_factory(normalized_ticker)

        try:
            # Request five calendar days so weekends and market holidays still
            # usually leave at least two actual daily closes to compare.
            history = provider_ticker.history(
                period="5d",
                interval="1d",
                auto_adjust=False,
                actions=False,
                timeout=self._timeout,
            )
            metadata = provider_ticker.get_history_metadata()
        except Exception as exc:
            raise PriceRequestError("price provider request failed") from exc

        if getattr(history, "empty", True):
            raise PriceNotFoundError(
                f"price provider returned no history for {normalized_ticker}"
            )

        try:
            close_values = history["Close"].dropna()
        except (KeyError, TypeError, AttributeError) as exc:
            raise PricePayloadError(
                "price provider response is missing closing prices"
            ) from exc

        if close_values.empty:
            raise PriceNotFoundError(
                f"price provider returned no closing prices for {normalized_ticker}"
            )

        # Negative indexes mean "last" and "second-to-last" values. Missing
        # closes were removed above, so these are real trading-day observations.
        latest_close = self._validate_price(close_values.iloc[-1])
        previous_close = (
            self._validate_price(close_values.iloc[-2])
            if len(close_values) >= 2
            else None
        )
        price_date = self._normalize_price_date(close_values.index[-1])
        currency = self._extract_currency(metadata)

        change: float | None = None
        change_percent: float | None = None
        # A single available close is still useful, but there is no honest daily
        # change to calculate until a previous close exists.
        if previous_close is not None:
            change = latest_close - previous_close
            change_percent = (change / previous_close) * 100

        return DailyPriceSnapshot(
            ticker=normalized_ticker,
            currency=currency,
            price_date=price_date,
            latest_close=latest_close,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
        )

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise ValueError("ticker must not be empty")
        return normalized_ticker

    @staticmethod
    def _validate_price(value: object) -> float:
        try:
            price = float(value)
        except (TypeError, ValueError) as exc:
            raise PricePayloadError(
                "price provider returned a non-numeric price"
            ) from exc

        if not math.isfinite(price) or price <= 0:
            raise PricePayloadError("price provider returned an invalid price")
        return price

    @staticmethod
    def _normalize_price_date(value: object) -> date:
        to_pydatetime = getattr(value, "to_pydatetime", None)
        if callable(to_pydatetime):
            value = to_pydatetime()

        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        raise PricePayloadError("price provider returned an invalid price date")

    @staticmethod
    def _extract_currency(metadata: object) -> str:
        if not isinstance(metadata, Mapping):
            raise PricePayloadError("price provider metadata must be an object")

        currency = metadata.get("currency")
        if not isinstance(currency, str) or not currency.strip():
            raise PricePayloadError("price provider metadata is missing currency")
        return currency.strip().upper()
