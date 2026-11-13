"""Typed boundary between Watchtower evidence and signal implementations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from watchtower.schemas import ResearchSignalResponse


@dataclass(frozen=True, slots=True)
class FilingFact:
    """One filing an engine may weigh: where to read it and when it was filed."""

    url: str
    filing_date: date


@dataclass(frozen=True, slots=True)
class HeadlineFact:
    """One headline an engine may weigh: where to read it and when it ran."""

    url: str
    published_at: datetime

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("headline publication time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ResearchSignalInput:
    """Normalized facts a signal engine may use without provider-specific data."""

    # Engines never read a clock. The caller states the moment the evidence
    # was gathered, so "how old is this filing" has one reproducible answer.
    as_of: datetime
    filing_provider: str
    filings: tuple[FilingFact, ...]
    headline_provider: str
    headlines: tuple[HeadlineFact, ...]
    price_provider: str
    price_change_percent: float | None

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("signal as-of time must be timezone-aware")
        # A signal input is assembled after provider normalization. Rejecting a
        # non-finite price here keeps every engine from needing this same guard.
        if self.price_change_percent is not None and not math.isfinite(
            self.price_change_percent
        ):
            raise ValueError("price change percent must be finite")


class ResearchSignalEngine(Protocol):
    """Public contract satisfied by the baseline and any future replacement."""

    def evaluate(self, signal_input: ResearchSignalInput) -> ResearchSignalResponse:
        """Return a source-grounded research-priority result for normalized facts."""
