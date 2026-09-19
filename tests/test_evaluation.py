"""A/P annotation tests use invented text, not scientific observations."""

import pytest
from pydantic import ValidationError

from autonomous_modality.evaluation import calculate_richness
from autonomous_modality.models import IdeaUnit, SolutionRichnessAnnotation


def annotation() -> SolutionRichnessAnnotation:
    """Return an illustrative proposed-analysis fixture."""
    return SolutionRichnessAnnotation(
        scenario_id="fixture",
        solution_id="fixture",
        annotator_id="test",
        annotator_kind="llm",
        source_text="  Compare profiles. Deposition may explain the relief.",
        ideas=[
            IdeaUnit(
                idea_id="a1",
                dimension="A",
                normalized_idea="Compare profiles",
                duplicate_group="method-1",
                source_start=2,
                source_end=19,
                status="proposed",
                relevant=True,
                scientific_validity="questionable",
                evidence_fidelity="not_applicable",
            )
        ],
    )


def test_count_is_separate_from_execution_and_quality() -> None:
    item = annotation()
    result = calculate_richness(item)
    assert result.analytical_approach_count == 1
    assert result.explanatory_perspective_count == 0
    assert "cross_modal" not in result.model_dump_json()
    assert item.source_text.startswith("  ")
    assert SolutionRichnessAnnotation.model_validate_json(item.model_dump_json()) == item


def test_duplicate_group_counted_once() -> None:
    item = annotation()
    duplicate = item.ideas[0].model_copy(update={"idea_id": "a2"})
    item.ideas = [*item.ideas, duplicate]
    assert calculate_richness(item).analytical_approach_count == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_start", -1),
        ("source_end", 999),
        ("source_end", 1),
        ("dimension", "C"),
        ("status", "guessed"),
    ],
)
def test_invalid_unit_rejected(field: str, value: object) -> None:
    payload = annotation().model_dump()
    payload["ideas"][0][field] = value
    with pytest.raises(ValidationError):
        SolutionRichnessAnnotation.model_validate(payload)


def test_conflicting_duplicate_group_rejected() -> None:
    payload = annotation().model_dump()
    payload["ideas"].append({**payload["ideas"][0], "idea_id": "p1", "dimension": "P"})
    with pytest.raises(ValidationError, match="conflicting"):
        SolutionRichnessAnnotation.model_validate(payload)


def test_legacy_three_dimension_input_rejected() -> None:
    payload = annotation().model_dump()
    payload["cross_modal_insights"] = []
    with pytest.raises(ValidationError):
        SolutionRichnessAnnotation.model_validate(payload)


def test_irrelevant_units_excluded_and_empty_annotations_allowed() -> None:
    item = annotation()
    item.ideas[0].relevant = False
    assert calculate_richness(item).analytical_approach_count == 0
    item.ideas = []
    assert calculate_richness(item).explanatory_perspective_count == 0
