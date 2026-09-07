"""Tests for deterministic richness-oriented modality selection."""

from itertools import combinations, permutations, product

import pytest

from autonomous_modality.models import (
    AssetAvailability,
    CraterQuestionType,
    DataAssetProfile,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
    SelectionPriority,
)
from autonomous_modality.selection import RULE_VERSION, filter_candidates, select_baseline


def test_repeated_capabilities_do_not_inflate_scores_or_expected_richness(
    selection_request: InputSelectionRequest,
) -> None:
    original = select_baseline(selection_request)
    request = selection_request.model_copy(deep=True)
    for asset in request.assets:
        asset.analytical_capabilities += [
            f"  {item.upper()}  " for item in asset.analytical_capabilities
        ]
        asset.explanatory_capabilities += [
            f"  {item.upper()}  " for item in asset.explanatory_capabilities
        ]
    actual = select_baseline(request)
    assert actual.scores == original.scores
    assert actual.decision == original.decision


def test_unavailable_asset_is_excluded_with_reason(
    selection_request: InputSelectionRequest,
) -> None:
    result = filter_candidates(selection_request)
    exclusion = next(
        item for item in result.exclusions if item.modality is InputDataModality.SIMULATION_OUTPUT
    )

    assert exclusion.reason_codes == ["ASSET_UNAVAILABLE"]


@pytest.mark.parametrize(
    ("question_type", "expected_first"),
    [
        (CraterQuestionType.ANALYTICAL_APPROACH_DISCOVERY, InputDataModality.TOPOGRAPHY),
        (
            CraterQuestionType.EXPLANATORY_PERSPECTIVE_EXPLORATION,
            InputDataModality.SCIENTIFIC_LITERATURE,
        ),
        (CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY, InputDataModality.TOPOGRAPHY),
    ],
)
def test_question_type_changes_first_selection(
    selection_request: InputSelectionRequest,
    question_type: CraterQuestionType,
    expected_first: InputDataModality,
) -> None:
    request = selection_request.model_copy(deep=True)
    request.question.question_type = question_type

    result = select_baseline(request)

    assert result.decision.selected[0].modality is expected_first


def test_selection_predicts_all_three_richness_dimensions(
    selection_request: InputSelectionRequest,
) -> None:
    result = select_baseline(selection_request)

    assert result.decision.expected_richness.analytical_approaches
    assert result.decision.expected_richness.explanatory_perspectives
    assert result.decision.expected_richness.cross_modal_insights


def test_required_modality_is_selected_first_and_marked_required(
    selection_request: InputSelectionRequest,
) -> None:
    request = selection_request.model_copy(deep=True)
    request.constraints.required_modalities = {InputDataModality.CRATER_CATALOG}

    result = select_baseline(request)

    assert result.decision.selected[0].modality is InputDataModality.CRATER_CATALOG
    assert result.decision.selected[0].priority is SelectionPriority.REQUIRED


def test_forbidden_modality_cannot_be_selected(
    selection_request: InputSelectionRequest,
) -> None:
    request = selection_request.model_copy(deep=True)
    request.constraints.forbidden_modalities = {InputDataModality.TOPOGRAPHY}

    result = select_baseline(request)
    selected = {item.modality for item in result.decision.selected}

    assert InputDataModality.TOPOGRAPHY not in selected
    assert any("MODALITY_FORBIDDEN" in item.reason_codes for item in result.candidates.exclusions)


def test_cost_budget_is_respected(selection_request: InputSelectionRequest) -> None:
    request = selection_request.model_copy(deep=True)
    request.constraints.maximum_total_cost = 2.0

    result = select_baseline(request)

    assert result.decision.total_cost <= 2.0


def test_required_modalities_cannot_collectively_exceed_budget(
    selection_request: InputSelectionRequest,
) -> None:
    request = selection_request.model_copy(deep=True)
    request.constraints = InputSelectionConstraints(
        maximum_modalities=2,
        maximum_total_cost=2.0,
        required_modalities={
            InputDataModality.OPTICAL_IMAGE,
            InputDataModality.CRATER_CATALOG,
        },
    )

    with pytest.raises(ValueError, match="required modalities exceed"):
        select_baseline(request)


def test_zero_budget_reports_that_no_combination_fits(
    selection_request: InputSelectionRequest,
) -> None:
    request = selection_request.model_copy(deep=True)
    request.constraints.maximum_total_cost = 0.0

    with pytest.raises(ValueError, match="leave no available"):
        select_baseline(request)


def test_cross_modal_task_rejects_single_modality_limit(
    selection_request: InputSelectionRequest,
) -> None:
    request = selection_request.model_copy(deep=True)
    request.question.question_type = CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY
    request.constraints.maximum_modalities = 1

    with pytest.raises(ValueError, match="requires at least two"):
        select_baseline(request)


def test_missing_required_modality_is_reported(
    selection_request: InputSelectionRequest,
) -> None:
    request = selection_request.model_copy(deep=True)
    request.constraints = InputSelectionConstraints(
        required_modalities={InputDataModality.SIMULATION_OUTPUT}
    )

    with pytest.raises(ValueError, match="required modalities are not available"):
        select_baseline(request)


def test_cross_modal_fallback_recovers_budget_feasible_pair(
    budget_trap_request: InputSelectionRequest,
) -> None:
    original = budget_trap_request.model_dump_json()

    result = select_baseline(budget_trap_request)

    assert [item.modality for item in result.decision.selected] == [
        InputDataModality.OPTICAL_IMAGE,
        InputDataModality.CRATER_CATALOG,
    ]
    assert result.decision.total_cost == 2.0
    assert result.rule_version == result.candidates.rule_version == RULE_VERSION
    assert RULE_VERSION == "input-richness-baseline-1.2"
    assert "CROSS_MODAL_FEASIBILITY_FALLBACK" in result.decision.reason_codes
    assert "does not optimize solution richness" in result.decision.rationale
    assert result.decision.expected_richness.cross_modal_insights[0].modalities == {
        InputDataModality.OPTICAL_IMAGE,
        InputDataModality.CRATER_CATALOG,
    }
    assert budget_trap_request.model_dump_json() == original


def test_fallback_uses_size_then_taxonomy_order_independent_of_input_order(
    budget_trap_request: InputSelectionRequest,
) -> None:
    budget_trap_request.assets[0].estimated_cost = 3.0
    budget_trap_request.constraints.maximum_total_cost = 3.0
    budget_trap_request.constraints.maximum_modalities = 3
    literature = DataAssetProfile(
        asset_id="fixture-literature",
        title="Metadata-only fixture",
        modality=InputDataModality.SCIENTIFIC_LITERATURE,
        estimated_cost=1.0,
        limitations=["Metadata-only fixture; no scientific data loaded or verified."],
    )
    baseline = None
    for assets in permutations([*budget_trap_request.assets, literature]):
        request = budget_trap_request.model_copy(deep=True)
        request.assets = list(assets)
        decision = select_baseline(request).decision
        assert [item.modality for item in decision.selected] == [
            InputDataModality.OPTICAL_IMAGE,
            InputDataModality.CRATER_CATALOG,
        ]
        assert decision.total_cost == 2.0
        if baseline is None:
            baseline = decision
        assert decision == baseline


@pytest.mark.parametrize("restriction", ["required", "forbidden", "unavailable", "budget"])
def test_fallback_never_relaxes_hard_constraints(
    budget_trap_request: InputSelectionRequest, restriction: str
) -> None:
    if restriction == "required":
        budget_trap_request.constraints.required_modalities = {InputDataModality.TOPOGRAPHY}
    elif restriction == "forbidden":
        budget_trap_request.constraints.forbidden_modalities = {InputDataModality.CRATER_CATALOG}
    elif restriction == "unavailable":
        budget_trap_request.assets[2].availability = AssetAvailability.UNAVAILABLE
    else:
        budget_trap_request.constraints.maximum_total_cost = 1.5

    with pytest.raises(ValueError, match="requires at least two"):
        select_baseline(budget_trap_request)


@pytest.mark.parametrize(
    ("question_type", "expected"),
    [
        (
            CraterQuestionType.ANALYTICAL_APPROACH_DISCOVERY,
            ["TOPOGRAPHY", "OPTICAL_IMAGE", "CRATER_CATALOG"],
        ),
        (
            CraterQuestionType.EXPLANATORY_PERSPECTIVE_EXPLORATION,
            ["SCIENTIFIC_LITERATURE", "OPTICAL_IMAGE", "TOPOGRAPHY"],
        ),
        (
            CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY,
            ["TOPOGRAPHY", "OPTICAL_IMAGE", "CRATER_CATALOG"],
        ),
        (
            CraterQuestionType.GENERAL_CRATER_INVESTIGATION,
            ["OPTICAL_IMAGE", "TOPOGRAPHY", "CRATER_CATALOG"],
        ),
    ],
)
def test_successful_greedy_choices_and_cost_are_preserved(
    selection_request: InputSelectionRequest,
    question_type: CraterQuestionType,
    expected: list[str],
) -> None:
    selection_request.question.question_type = question_type
    decision = select_baseline(selection_request).decision

    assert [item.modality.value for item in decision.selected] == expected
    assert decision.total_cost == 5.0
    assert decision.reason_codes == ["RICHNESS_ORIENTED_DETERMINISTIC_BASELINE"]


def test_non_cross_modal_greedy_selection_does_not_trigger_fallback(
    budget_trap_request: InputSelectionRequest,
) -> None:
    budget_trap_request.question.question_type = CraterQuestionType.ANALYTICAL_APPROACH_DISCOVERY

    decision = select_baseline(budget_trap_request).decision

    assert [item.modality for item in decision.selected] == [InputDataModality.TOPOGRAPHY]
    assert "CROSS_MODAL_FEASIBILITY_FALLBACK" not in decision.reason_codes


@pytest.mark.parametrize("costs", list(product((0.0, 1.0, 2.0), repeat=3)))
def test_cross_modal_selection_matches_exhaustive_feasibility(
    budget_trap_request: InputSelectionRequest, costs: tuple[float, float, float]
) -> None:
    """Check 1,620 metadata-only cases, including free assets and impossible requests."""
    for asset, cost in zip(budget_trap_request.assets, costs, strict=True):
        asset.estimated_cost = cost
    for budget, limit, required, forbidden in product(
        range(5), range(1, 4), (False, True), (False, True)
    ):
        constraints = InputSelectionConstraints(
            maximum_total_cost=budget,
            maximum_modalities=limit,
            required_modalities={InputDataModality.TOPOGRAPHY} if required else set(),
            forbidden_modalities={InputDataModality.CRATER_CATALOG} if forbidden else set(),
        )
        budget_trap_request.constraints = constraints
        feasible = [
            group
            for size in range(2, limit + 1)
            for group in combinations(budget_trap_request.assets, size)
            if constraints.required_modalities.issubset(asset.modality for asset in group)
            and not constraints.forbidden_modalities.intersection(asset.modality for asset in group)
            and sum(asset.estimated_cost for asset in group) <= budget
        ]
        if not feasible:
            with pytest.raises(ValueError):
                select_baseline(budget_trap_request)
            continue
        decision = select_baseline(budget_trap_request).decision
        selected = {item.modality for item in decision.selected}
        assert any(selected == {asset.modality for asset in group} for group in feasible)
        assert decision.total_cost <= budget
        if required:
            assert decision.selected[0].modality is InputDataModality.TOPOGRAPHY
            assert decision.selected[0].priority is SelectionPriority.REQUIRED
