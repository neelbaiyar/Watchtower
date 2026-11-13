"""Public, deterministic research-priority baseline."""

from __future__ import annotations

from datetime import UTC, timedelta

from watchtower.schemas import (
    ResearchPriority,
    ResearchSignalResponse,
    SignalEvidenceResponse,
)
from watchtower.signals.contracts import ResearchSignalInput


class TransparentResearchSignalEngine:
    """Score visible activity without inferring sentiment or future returns."""

    LIMITATION = (
        "Research-priority signal only; not investment advice or a price prediction."
    )
    # "Recent" needs a boundary. Providers return the newest items they have,
    # however old, so without these windows almost every company would score
    # as busy. An 8-K stays relevant to research for about a month; headline
    # attention fades within a week.
    FILING_WINDOW_DAYS = 30
    HEADLINE_WINDOW_DAYS = 7

    def evaluate(self, signal_input: ResearchSignalInput) -> ResearchSignalResponse:
        """Build one reproducible signal from filing, headline, and price facts."""

        evidence = self._evidence(signal_input)
        attention_score = min(sum(item.points for item in evidence), 100)
        level = self._level_for(attention_score)

        return ResearchSignalResponse(
            level=level,
            attention_score=attention_score,
            explanation=self._explanation(level, attention_score, evidence),
            evidence=evidence,
            limitation=self.LIMITATION,
        )

    @classmethod
    def _evidence(
        cls,
        signal_input: ResearchSignalInput,
    ) -> list[SignalEvidenceResponse]:
        evidence: list[SignalEvidenceResponse] = []

        # Filing dates carry no time zone, so compare whole calendar days
        # against the UTC date of the snapshot. A date that reads as slightly
        # in the future because of that offset still counts as recent.
        as_of_date = signal_input.as_of.astimezone(UTC).date()
        recent_filing_urls = [
            filing.url
            for filing in signal_input.filings
            if (as_of_date - filing.filing_date).days <= cls.FILING_WINDOW_DAYS
        ]
        filing_count = len(recent_filing_urls)
        if filing_count:
            # The first three filings receive equal weight. A fourth or later
            # filing earns a small extra amount while preventing one source
            # type from consuming the entire 100-point score.
            filing_points = min(filing_count, 3) * 12 + (4 if filing_count >= 4 else 0)
            evidence.append(
                SignalEvidenceResponse(
                    category="filing_activity",
                    source_provider=signal_input.filing_provider,
                    source_urls=recent_filing_urls,
                    points=filing_points,
                    summary=(
                        f"Snapshot contains {filing_count} 8-K filing"
                        f"{'s' if filing_count != 1 else ''} from the last "
                        f"{cls.FILING_WINDOW_DAYS} days."
                    ),
                )
            )

        headline_window = timedelta(days=cls.HEADLINE_WINDOW_DAYS)
        recent_headline_urls = [
            headline.url
            for headline in signal_input.headlines
            if signal_input.as_of - headline.published_at <= headline_window
        ]
        headline_count = len(recent_headline_urls)
        if headline_count:
            headline_points = min(headline_count, 3) * 6
            evidence.append(
                SignalEvidenceResponse(
                    category="headline_activity",
                    source_provider=signal_input.headline_provider,
                    source_urls=recent_headline_urls,
                    points=headline_points,
                    summary=(
                        f"Snapshot contains {headline_count} ticker-associated headline"
                        f"{'s' if headline_count != 1 else ''} from the last "
                        f"{cls.HEADLINE_WINDOW_DAYS} days."
                    ),
                )
            )

        if signal_input.price_change_percent is not None:
            movement = abs(signal_input.price_change_percent)
            price_points = cls._price_points(movement)
            if price_points:
                evidence.append(
                    SignalEvidenceResponse(
                        category="price_movement",
                        source_provider=signal_input.price_provider,
                        # The current price adapter does not provide an
                        # inspectable source URL, so this evidence names its
                        # provider and intentionally carries no invented link.
                        source_urls=[],
                        points=price_points,
                        summary=(
                            f"Latest daily close moved {movement:.2f}% in magnitude."
                        ),
                    )
                )

        return evidence

    @staticmethod
    def _price_points(movement: float) -> int:
        """Map absolute daily movement to attention points, not direction."""

        if movement >= 5:
            return 42
        if movement >= 3:
            return 30
        if movement >= 1:
            return 18
        if movement >= 0.25:
            return 8
        return 0

    @staticmethod
    def _level_for(attention_score: int) -> ResearchPriority:
        """Translate the bounded score into one non-predictive ordinal level."""

        if attention_score == 0:
            return ResearchPriority.QUIET
        if attention_score <= 24:
            return ResearchPriority.LOW_ATTENTION
        if attention_score <= 49:
            return ResearchPriority.MONITOR
        if attention_score <= 74:
            return ResearchPriority.ELEVATED_ATTENTION
        return ResearchPriority.HIGH_ATTENTION

    @staticmethod
    def _explanation(
        level: ResearchPriority,
        attention_score: int,
        evidence: list[SignalEvidenceResponse],
    ) -> str:
        """State the result and its observable inputs without interpretation."""

        label = level.value.replace("_", " ")
        if not evidence:
            return (
                f"{label.capitalize()} research attention (0/100): the snapshot "
                "contains no weighted filing, headline, or price-movement evidence."
            )

        summaries = " ".join(item.summary for item in evidence)
        return (
            f"{label.capitalize()} research attention ({attention_score}/100). "
            f"{summaries}"
        )
