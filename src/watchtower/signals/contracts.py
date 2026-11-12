"""Typed boundary between Watchtower evidence and signal implementations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from watchtower.schemas import ResearchSignalResponse


@dataclass(frozen=True, slots=True)
class ResearchSignalInput:
    """Normalized facts a signal engine may use without provider-specific data."""

    filing_provider: str
    filing_urls: tuple[str, ...]
    headline_provider: str
    headline_urls: tuple[str, ...]
    price_provider: str
    price_change_percent: float | None

    def __post_init__(self) -> None:
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
