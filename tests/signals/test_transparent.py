"""Pure unit tests for the public transparent research-signal baseline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from watchtower.schemas import ResearchPriority
from watchtower.signals import (
    FilingFact,
    HeadlineFact,
    ResearchSignalInput,
    TransparentResearchSignalEngine,
)

AS_OF = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)


def signal_input(
    *,
    filing_count: int = 0,
    headline_count: int = 0,
    price_change_percent: float | None = None,
    filing_age_days: int = 1,
    headline_age: timedelta = timedelta(hours=1),
) -> ResearchSignalInput:
    """Create normalized evidence without calling any external provider."""

    return ResearchSignalInput(
        as_of=AS_OF,
        filing_provider="SEC EDGAR",
        filings=tuple(
            FilingFact(
                url=f"https://www.sec.gov/Archives/example/{index}",
                filing_date=AS_OF.date() - timedelta(days=filing_age_days),
            )
            for index in range(filing_count)
        ),
        headline_provider="Marketaux",
        headlines=tuple(
            HeadlineFact(
                url=f"https://example.com/article/{index}",
                published_at=AS_OF - headline_age,
            )
            for index in range(headline_count)
        ),
        price_provider="Yahoo Finance via yfinance",
        price_change_percent=price_change_percent,
    )


@pytest.mark.parametrize(
    ("signal_input_kwargs", "expected_score", "expected_level"),
    [
        ({}, 0, ResearchPriority.QUIET),
        ({"filing_count": 1}, 12, ResearchPriority.LOW_ATTENTION),
        (
            {"filing_count": 2, "headline_count": 1},
            30,
            ResearchPriority.MONITOR,
        ),
        (
            {"filing_count": 3, "headline_count": 3},
            54,
            ResearchPriority.ELEVATED_ATTENTION,
        ),
        (
            {"filing_count": 4, "headline_count": 3, "price_change_percent": 5},
            100,
            ResearchPriority.HIGH_ATTENTION,
        ),
    ],
)
def test_transparent_engine_maps_evidence_to_five_levels(
    signal_input_kwargs: dict[str, int | float],
    expected_score: int,
    expected_level: ResearchPriority,
) -> None:
    result = TransparentResearchSignalEngine().evaluate(
        signal_input(**signal_input_kwargs)
    )

    assert result.attention_score == expected_score
    assert result.level is expected_level
    assert "investment advice" in result.limitation
    assert "prediction" in result.limitation


def test_price_movement_uses_magnitude_not_direction() -> None:
    engine = TransparentResearchSignalEngine()

    positive = engine.evaluate(signal_input(price_change_percent=3.5))
    negative = engine.evaluate(signal_input(price_change_percent=-3.5))

    assert positive.attention_score == negative.attention_score == 30
    assert positive.evidence[0].summary == negative.evidence[0].summary


def test_signal_retains_source_links_for_filings_and_headlines() -> None:
    result = TransparentResearchSignalEngine().evaluate(
        signal_input(filing_count=1, headline_count=1)
    )

    assert result.evidence[0].source_provider == "SEC EDGAR"
    assert str(result.evidence[0].source_urls[0]).startswith("https://www.sec.gov/")
    assert result.evidence[1].source_provider == "Marketaux"
    assert str(result.evidence[1].source_urls[0]).startswith("https://example.com/")


def test_signal_is_deterministic_for_identical_input() -> None:
    engine = TransparentResearchSignalEngine()
    evidence = signal_input(filing_count=2, headline_count=2, price_change_percent=1.5)

    assert engine.evaluate(evidence) == engine.evaluate(evidence)


def test_signal_input_rejects_non_finite_price_change() -> None:
    with pytest.raises(ValueError, match="finite"):
        signal_input(price_change_percent=float("nan"))


def test_same_activity_scores_elevated_only_while_it_is_recent() -> None:
    engine = TransparentResearchSignalEngine()

    # Five 8-Ks and three headlines is what the providers return for almost
    # any active company, however long ago those items appeared.
    recent = engine.evaluate(signal_input(filing_count=5, headline_count=3))
    old = engine.evaluate(
        signal_input(
            filing_count=5,
            headline_count=3,
            filing_age_days=200,
            headline_age=timedelta(days=45),
        )
    )

    assert recent.attention_score == 58
    assert recent.level is ResearchPriority.ELEVATED_ATTENTION
    assert old.attention_score == 0
    assert old.level is ResearchPriority.QUIET
    assert old.evidence == []


def test_old_filings_alone_do_not_raise_attention() -> None:
    result = TransparentResearchSignalEngine().evaluate(
        signal_input(filing_count=5, headline_count=3, filing_age_days=120)
    )

    assert result.attention_score == 18
    assert result.level is ResearchPriority.LOW_ATTENTION
    assert [item.category for item in result.evidence] == ["headline_activity"]


@pytest.mark.parametrize(
    ("filing_age_days", "expected_points"),
    [(0, 12), (30, 12), (31, 0), (-1, 12)],
)
def test_filing_window_is_thirty_days_inclusive(
    filing_age_days: int,
    expected_points: int,
) -> None:
    result = TransparentResearchSignalEngine().evaluate(
        signal_input(filing_count=1, filing_age_days=filing_age_days)
    )

    assert result.attention_score == expected_points


@pytest.mark.parametrize(
    ("headline_age", "expected_points"),
    [
        (timedelta(0), 6),
        (timedelta(days=7), 6),
        (timedelta(days=7, seconds=1), 0),
    ],
)
def test_headline_window_is_seven_days_inclusive(
    headline_age: timedelta,
    expected_points: int,
) -> None:
    result = TransparentResearchSignalEngine().evaluate(
        signal_input(headline_count=1, headline_age=headline_age)
    )

    assert result.attention_score == expected_points


def test_evidence_links_only_the_items_inside_the_window() -> None:
    mixed = ResearchSignalInput(
        as_of=AS_OF,
        filing_provider="SEC EDGAR",
        filings=(
            FilingFact(
                url="https://www.sec.gov/Archives/example/new",
                filing_date=AS_OF.date() - timedelta(days=3),
            ),
            FilingFact(
                url="https://www.sec.gov/Archives/example/old",
                filing_date=AS_OF.date() - timedelta(days=90),
            ),
        ),
        headline_provider="Marketaux",
        headlines=(),
        price_provider="Yahoo Finance via yfinance",
        price_change_percent=None,
    )

    result = TransparentResearchSignalEngine().evaluate(mixed)

    assert result.attention_score == 12
    assert [str(url) for url in result.evidence[0].source_urls] == [
        "https://www.sec.gov/Archives/example/new"
    ]
    assert result.evidence[0].summary == (
        "Snapshot contains 1 8-K filing from the last 30 days."
    )


def test_signal_input_rejects_naive_times() -> None:
    naive = datetime(2026, 9, 25, 16, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        HeadlineFact(url="https://example.com/article", published_at=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        ResearchSignalInput(
            as_of=naive,
            filing_provider="SEC EDGAR",
            filings=(),
            headline_provider="Marketaux",
            headlines=(),
            price_provider="Yahoo Finance via yfinance",
            price_change_percent=None,
        )
