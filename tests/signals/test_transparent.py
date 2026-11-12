"""Pure unit tests for the public transparent research-signal baseline."""

from __future__ import annotations

import pytest

from watchtower.schemas import ResearchPriority
from watchtower.signals import ResearchSignalInput, TransparentResearchSignalEngine


def signal_input(
    *,
    filing_count: int = 0,
    headline_count: int = 0,
    price_change_percent: float | None = None,
) -> ResearchSignalInput:
    """Create normalized evidence without calling any external provider."""

    return ResearchSignalInput(
        filing_provider="SEC EDGAR",
        filing_urls=tuple(
            f"https://www.sec.gov/Archives/example/{index}"
            for index in range(filing_count)
        ),
        headline_provider="Marketaux",
        headline_urls=tuple(
            f"https://example.com/article/{index}" for index in range(headline_count)
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
