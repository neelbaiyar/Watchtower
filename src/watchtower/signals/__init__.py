"""Deterministic, source-grounded research-priority signals."""

from watchtower.signals.contracts import ResearchSignalEngine, ResearchSignalInput
from watchtower.signals.transparent import TransparentResearchSignalEngine

__all__ = [
    "ResearchSignalEngine",
    "ResearchSignalInput",
    "TransparentResearchSignalEngine",
]
