from collections import UserDict
from datetime import date

import pandas as pd
import pytest

from watchtower.clients.yfinance import (
    PriceNotFoundError,
    PriceRequestError,
    YFinanceClient,
)


class FakeTicker:
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
