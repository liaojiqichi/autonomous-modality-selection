"""Primary conditions use metadata fixtures and never invoke a model."""

import pytest
from pydantic import ValidationError

from autonomous_modality.experiments import (
    ExperimentCondition as C,
)
from autonomous_modality.experiments import (
    ExperimentSelection,
    prepare_condition,
)
from autonomous_modality.models import (
    AssetAvailability,
    CraterQuestion,
    CraterQuestionType,
    DataAssetProfile,
    InputSelectionConstraints,
    InputSelectionRequest,
)
from autonomous_modality.models import (
    InputDataModality as M,
)


@pytest.fixture
def request_data() -> InputSelectionRequest:
    """Three invented assets; their existence is an explicit test assumption."""
    return InputSelectionRequest(
        question=CraterQuestion(
            question_id="fixture",
            text="Investigate alternatives",
            question_type=CraterQuestionType.GENERAL_CRATER_INVESTIGATION,
        ),
        assets=[
            DataAssetProfile(
                asset_id=m.value, title="Metadata fixture", modality=m, estimated_cost=cost
            )
            for m, cost in [(M.CRATER_CATALOG, 1), (M.OPTICAL_IMAGE, 2), (M.TOPOGRAPHY, 2)]
        ],
        constraints=InputSelectionConstraints(maximum_total_cost=3, maximum_modalities=2),
    )


@pytest.mark.parametrize("condition", list(C))
def test_primary_conditions(request_data: InputSelectionRequest, condition: C) -> None:
    result = prepare_condition(request_data, condition, 42)
    assert ExperimentSelection.model_validate_json(result.model_dump_json()) == result
    assert not result.llm_called
    if condition == C.NO_DATA:
        assert result.status == "ready" and result.selected_asset_ids == []
    elif condition == C.ALL_AVAILABLE:
        assert len(result.selected_asset_ids) == 3 and result.total_cost == 5
    elif condition == C.RANDOM:
        assert 1 <= len(result.selected_asset_ids) <= 2 and result.total_cost <= 3
    else:
        assert result.status == "pending_agent" and not result.selected_asset_ids


def test_random_reproducible_order_independent_and_constraints(
    request_data: InputSelectionRequest,
) -> None:
    first = prepare_condition(request_data, C.RANDOM, 17)
    request_data.assets.reverse()
    assert prepare_condition(request_data, C.RANDOM, 17) == first
    assert (
        len(
            {
                tuple(prepare_condition(request_data, C.RANDOM, s).selected_asset_ids)
                for s in range(30)
            }
        )
        > 1
    )
    request_data.constraints.required_modalities = {M.OPTICAL_IMAGE}
    request_data.constraints.forbidden_modalities = {M.TOPOGRAPHY}
    for seed in range(20):
        result = prepare_condition(request_data, C.RANDOM, seed)
        assert M.OPTICAL_IMAGE.value in result.selected_asset_ids
        assert M.TOPOGRAPHY.value not in result.selected_asset_ids


@pytest.mark.parametrize("condition", [C.RANDOM, C.AGENT])
def test_infeasible_not_empty_control(request_data: InputSelectionRequest, condition: C) -> None:
    request_data.constraints.maximum_total_cost = 0
    result = prepare_condition(request_data, condition)
    assert result.status == "infeasible" and result.reason_codes == ["NO_FEASIBLE_SUBSET"]
    assert prepare_condition(request_data, C.NO_DATA).status == "ready"


def test_unverified_assets_excluded(request_data: InputSelectionRequest) -> None:
    request_data.assets[0].availability = AssetAvailability.CASE_SPECIFIC
    request_data.assets[1].availability = AssetAvailability.UNAVAILABLE
    assert prepare_condition(request_data, C.ALL_AVAILABLE).selected_asset_ids == [M.TOPOGRAPHY]
    request_data.constraints.required_modalities = {M.OPTICAL_IMAGE}
    assert prepare_condition(request_data, C.AGENT).status == "infeasible"


@pytest.mark.parametrize("seed", [-1, True, 1.5])
def test_invalid_seed(request_data: InputSelectionRequest, seed: int) -> None:
    with pytest.raises(ValueError, match="seed"):
        prepare_condition(request_data, C.RANDOM, seed)


def test_reject_fabricated_agent_and_empty_random() -> None:
    for condition in [C.AGENT, C.RANDOM]:
        with pytest.raises(ValidationError):
            ExperimentSelection(
                condition=condition, status="ready", seed=0, reason_codes=["fixture"]
            )
