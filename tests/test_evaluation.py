"""Tests for the three-dimensional solution-richness measurements."""

import pytest
from pydantic import ValidationError

from autonomous_modality.evaluation import RULE_VERSION, calculate_richness
from autonomous_modality.models import (
    CrossModalInsight,
    CrossModalInsightLevel,
    InputDataModality,
    RichnessScores,
    SolutionRichnessAnnotation,
)


def test_richness_counts_distinct_items_and_weights_synthesis() -> None:
    annotation = SolutionRichnessAnnotation(
        scenario_id="scenario-1",
        solution_id="solution-1",
        annotator_id="expert-1",
        analytical_approaches=["Morphometry", "morphometry", "Spectral comparison"],
        explanatory_perspectives=["Target material", "Impact process"],
        cross_modal_insights=[
            CrossModalInsight(
                modalities={InputDataModality.OPTICAL_IMAGE, InputDataModality.TOPOGRAPHY},
                description="Visible and elevation structures correspond.",
                level=CrossModalInsightLevel.CORRESPONDENCE,
            ),
            CrossModalInsight(
                modalities={
                    InputDataModality.TOPOGRAPHY,
                    InputDataModality.SIMULATION_OUTPUT,
                },
                description="Observed relief motivates a simulated formation hypothesis.",
                level=CrossModalInsightLevel.SYNTHESIS,
            ),
            CrossModalInsight(
                modalities={InputDataModality.OPTICAL_IMAGE, InputDataModality.CRATER_CATALOG},
                description="The two inputs are listed independently.",
                level=CrossModalInsightLevel.JUXTAPOSITION,
            ),
        ],
    )

    scores = calculate_richness(annotation)

    assert scores.analytical_approach_count == 2
    assert scores.explanatory_perspective_count == 2
    assert scores.cross_modal_correspondence_count == 1
    assert scores.cross_modal_synthesis_count == 1
    assert scores.weighted_cross_modal_score == 3.0


def _annotation(insights: list[CrossModalInsight]) -> SolutionRichnessAnnotation:
    return SolutionRichnessAnnotation(
        scenario_id="metadata-only-evaluation-fixture",
        solution_id="illustrative-not-observed",
        annotator_id="test-fixture",
        cross_modal_insights=insights,
    )


@pytest.mark.parametrize(
    ("level", "weight"),
    [
        (CrossModalInsightLevel.JUXTAPOSITION, 0.0),
        (CrossModalInsightLevel.CORRESPONDENCE, 1.0),
        (CrossModalInsightLevel.SYNTHESIS, 2.0),
    ],
)
def test_duplicate_insights_count_once_without_mutating_annotation(
    level: CrossModalInsightLevel, weight: float
) -> None:
    modalities = [InputDataModality.OPTICAL_IMAGE, InputDataModality.TOPOGRAPHY]
    first = CrossModalInsight(
        modalities=set(modalities), description="Illustrative statement.", level=level
    )
    duplicate = CrossModalInsight(
        modalities=set(reversed(modalities)), description="  ILLUSTRATIVE STATEMENT.  ", level=level
    )
    annotation = _annotation([first, first.model_copy(deep=True), duplicate])
    original = annotation.model_dump_json()

    scores = calculate_richness(annotation)

    assert scores == calculate_richness(_annotation([first]))
    assert scores.weighted_cross_modal_score == weight
    assert annotation.model_dump_json() == original


@pytest.mark.parametrize("difference", ["modalities", "description", "level"])
def test_deduplication_requires_same_modalities_description_and_level(difference: str) -> None:
    first = CrossModalInsight(
        modalities={InputDataModality.OPTICAL_IMAGE, InputDataModality.TOPOGRAPHY},
        description="Illustrative relation between image and elevation.",
        level=CrossModalInsightLevel.SYNTHESIS,
    )
    second = first.model_copy(deep=True)
    if difference == "modalities":
        second.modalities = {InputDataModality.OPTICAL_IMAGE, InputDataModality.CRATER_CATALOG}
    elif difference == "description":
        second.description = "Illustrative relation between elevation and image."
    else:
        second.level = CrossModalInsightLevel.CORRESPONDENCE

    scores = calculate_richness(_annotation([first, second]))

    # Semantic equivalence and conflicting levels require human annotation review.
    assert scores.cross_modal_correspondence_count + scores.cross_modal_synthesis_count == 2
    assert scores.weighted_cross_modal_score == (3.0 if difference == "level" else 4.0)


def test_empty_annotation_produces_versioned_zero_scores() -> None:
    scores = calculate_richness(_annotation([]))

    assert scores.rule_version == RULE_VERSION == "solution-richness-counts-1.1"
    assert scores.analytical_approach_count == scores.explanatory_perspective_count == 0
    assert scores.cross_modal_correspondence_count == scores.cross_modal_synthesis_count == 0
    assert scores.weighted_cross_modal_score == 0.0
    assert RichnessScores.model_validate_json(scores.model_dump_json()) == scores


def test_legacy_score_payload_is_readable_without_inventing_rule_version() -> None:
    legacy_payload = calculate_richness(_annotation([])).model_dump(exclude={"rule_version"})

    scores = RichnessScores.model_validate(legacy_payload)

    assert scores.rule_version is None
    assert scores.model_dump(exclude={"rule_version"}) == legacy_payload


@pytest.mark.parametrize("version", ["", "   ", 123])
def test_invalid_score_rule_version_is_rejected(version: object) -> None:
    payload = calculate_richness(_annotation([])).model_dump()
    payload["rule_version"] = version

    with pytest.raises(ValidationError):
        RichnessScores.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("description", "   "), ("level", "INVENTED_LEVEL"), ("modalities", ["OPTICAL_IMAGE"])],
)
def test_invalid_insights_are_rejected_before_scoring(field: str, value: object) -> None:
    payload = {
        "modalities": ["OPTICAL_IMAGE", "TOPOGRAPHY"],
        "description": "Metadata-only annotation fixture.",
        "level": "SYNTHESIS",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        CrossModalInsight.model_validate(payload)
