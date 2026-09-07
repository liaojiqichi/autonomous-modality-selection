"""Validation tests for the revised input-modality domain contracts."""

import pytest
from pydantic import ValidationError

from autonomous_modality.models import (
    CraterQuestion,
    CraterQuestionType,
    DataAssetProfile,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
    SpatialCoverage,
)


def test_request_round_trips_as_schema_v2(selection_request: InputSelectionRequest) -> None:
    payload = selection_request.model_dump_json()
    restored = InputSelectionRequest.model_validate_json(payload)

    assert restored == selection_request
    assert restored.schema_version == "2.0"


def test_spatial_coverage_rejects_inverted_bounds() -> None:
    with pytest.raises(ValidationError, match="minimum latitude"):
        SpatialCoverage(minimum_latitude=20.0, maximum_latitude=-20.0)


def test_constraints_reject_required_forbidden_overlap() -> None:
    with pytest.raises(ValidationError, match="both required and forbidden"):
        InputSelectionConstraints(
            required_modalities={InputDataModality.TOPOGRAPHY},
            forbidden_modalities={InputDataModality.TOPOGRAPHY},
        )


def test_request_rejects_duplicate_modalities() -> None:
    assets = [
        DataAssetProfile(
            asset_id="image-a",
            modality=InputDataModality.OPTICAL_IMAGE,
            title="Image A",
        ),
        DataAssetProfile(
            asset_id="image-b",
            modality=InputDataModality.OPTICAL_IMAGE,
            title="Image B",
        ),
    ]
    with pytest.raises(ValidationError, match="unique modalities"):
        InputSelectionRequest(
            question=CraterQuestion(
                question_id="q1",
                text="Propose approaches.",
                question_type=CraterQuestionType.ANALYTICAL_APPROACH_DISCOVERY,
            ),
            assets=assets,
        )


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        DataAssetProfile.model_validate(
            {
                "asset_id": "catalog",
                "modality": "CRATER_CATALOG",
                "title": "Catalog",
                "invented_field": True,
            }
        )


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_costs_are_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        InputSelectionConstraints(maximum_total_cost=value)
    with pytest.raises(ValidationError):
        DataAssetProfile(
            asset_id="fixture",
            title="Synthetic fixture",
            modality=InputDataModality.CRATER_CATALOG,
            estimated_cost=value,
        )


def test_duplicate_asset_ids_are_rejected(selection_request: InputSelectionRequest) -> None:
    payload = selection_request.model_dump()
    payload["assets"][1]["asset_id"] = payload["assets"][0]["asset_id"]
    with pytest.raises(ValidationError, match="unique asset IDs"):
        InputSelectionRequest.model_validate(payload)
