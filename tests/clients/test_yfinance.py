"""Price-client tests using a minimal stand-in for yfinance's ticker object."""

from collections import UserDict
from datetime import date

import pandas as pd
import pytest

from watchtower.clients.yfinance import (
    PriceNotFoundError,
    PricePayloadError,
    PriceRequestError,
    YFinanceClient,
)


class FakeTicker:
    # The fake returns a pandas table because that is the external shape the
    # real adapter must translate, but it never contacts Yahoo Finance.
    def __init__(
        self,
        history: pd.DataFrame,
        *,
        metadata: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self._history = history
        self._metadata = metadata if metadata is not None else {"currency": "USD"}
        self._error = error
        self.history_kwargs: dict[str, object] | None = None

    def history(self, **kwargs: object) -> pd.DataFrame:
        self.history_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._history

    def get_history_metadata(self) -> object:
        return self._metadata


def test_daily_price_is_normalized_from_history() -> None:
    history = pd.DataFrame(
        {"Close": [100.0, 102.0]},
        index=pd.to_datetime(["2026-09-24", "2026-09-25"], utc=True),
    )
    fake_ticker = FakeTicker(history, metadata=UserDict({"currency": "USD"}))
    requested_tickers: list[str] = []

    # Factory injection lets the test observe ticker normalization and supply
    # one controlled provider object.
    def ticker_factory(ticker: str) -> FakeTicker:
        requested_tickers.append(ticker)
        return fake_ticker

    client = YFinanceClient(ticker_factory=ticker_factory)
    quote = client.get_daily_price(" aapl ")

    assert requested_tickers == ["AAPL"]
    assert quote.ticker == "AAPL"
    assert quote.currency == "USD"
    assert quote.price_date == date(2026, 9, 25)
    assert quote.latest_close == 102.0
    assert quote.previous_close == 100.0
    assert quote.change == 2.0
    assert quote.change_percent == 2.0
    assert fake_ticker.history_kwargs == {
        "period": "5d",
        "interval": "1d",
        "auto_adjust": False,
        "actions": False,
        "timeout": 10.0,
    }


def test_empty_history_raises_owned_not_found_error() -> None:
    fake_ticker = FakeTicker(pd.DataFrame())
    client = YFinanceClient(ticker_factory=lambda _: fake_ticker)

    with pytest.raises(PriceNotFoundError, match="UNKNOWN"):
        client.get_daily_price("unknown")


def test_provider_failure_does_not_leak_details() -> None:
    fake_ticker = FakeTicker(
        pd.DataFrame(),
        error=RuntimeError("provider-internal-details"),
    )
    client = YFinanceClient(ticker_factory=lambda _: fake_ticker)

    with pytest.raises(PriceRequestError) as error:
        client.get_daily_price("HPE")

    assert str(error.value) == "price provider request failed"
    assert "provider-internal-details" not in str(error.value)


def test_single_close_has_no_daily_change() -> None:
    history = pd.DataFrame(
        {"Close": [float("nan"), 102.0]},
        index=pd.to_datetime(["2026-09-24", "2026-09-25"], utc=True),
    )
    client = YFinanceClient(ticker_factory=lambda _: FakeTicker(history))

    quote = client.get_daily_price("HPE")

    assert quote.latest_close == 102.0
    assert quote.previous_close is None
    assert quote.change is None
    assert quote.change_percent is None


@pytest.mark.parametrize(
    ("closes", "metadata"),
    [
        ([100.0, 0.0], {"currency": "USD"}),
        ([100.0, -5.0], {"currency": "USD"}),
        ([100.0, float("inf")], {"currency": "USD"}),
        ([100.0, 102.0], {}),
        ([100.0, 102.0], {"currency": "  "}),
        ([100.0, 102.0], ["USD"]),
    ],
)
def test_unusable_price_data_raises_owned_payload_error(
    closes: list[float],
    metadata: object,
) -> None:
    history = pd.DataFrame(
        {"Close": closes},
        index=pd.to_datetime(["2026-09-24", "2026-09-25"], utc=True),
    )
    client = YFinanceClient(
        ticker_factory=lambda _: FakeTicker(history, metadata=metadata)
    )

    with pytest.raises(PricePayloadError):
        client.get_daily_price("HPE")


def test_history_without_a_close_column_raises_owned_payload_error() -> None:
    history = pd.DataFrame(
        {"Open": [100.0]},
        index=pd.to_datetime(["2026-09-25"], utc=True),
    )
    client = YFinanceClient(ticker_factory=lambda _: FakeTicker(history))

    with pytest.raises(PricePayloadError):
        client.get_daily_price("HPE")
