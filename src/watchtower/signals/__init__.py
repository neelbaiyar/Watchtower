"""Deterministic, source-grounded research-priority signals."""

from watchtower.signals.contracts import (
    FilingFact,
    HeadlineFact,
    ResearchSignalEngine,
    ResearchSignalInput,
)
from watchtower.signals.transparent import TransparentResearchSignalEngine

__all__ = [
    "FilingFact",
    "HeadlineFact",
    "ResearchSignalEngine",
    "ResearchSignalInput",
    "TransparentResearchSignalEngine",
]
