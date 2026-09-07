"""Deterministic solution-richness measurements for annotated outputs."""

from autonomous_modality.models import (
    CrossModalInsightLevel,
    RichnessScores,
    SolutionRichnessAnnotation,
)

RULE_VERSION = "solution-richness-counts-1.1"


def _distinct_count(items: list[str]) -> int:
    return len({item.casefold().strip() for item in items})


def calculate_richness(annotation: SolutionRichnessAnnotation) -> RichnessScores:
    """Count distinct items without changing annotations or merging paraphrases."""
    distinct_insights = {
        (frozenset(item.modalities), item.description.casefold().strip(), item.level)
        for item in annotation.cross_modal_insights
    }
    correspondence = sum(
        level is CrossModalInsightLevel.CORRESPONDENCE for _, _, level in distinct_insights
    )
    synthesis = sum(level is CrossModalInsightLevel.SYNTHESIS for _, _, level in distinct_insights)
    return RichnessScores(
        rule_version=RULE_VERSION,
        analytical_approach_count=_distinct_count(annotation.analytical_approaches),
        explanatory_perspective_count=_distinct_count(annotation.explanatory_perspectives),
        cross_modal_correspondence_count=correspondence,
        cross_modal_synthesis_count=synthesis,
        weighted_cross_modal_score=float(correspondence + 2 * synthesis),
    )
