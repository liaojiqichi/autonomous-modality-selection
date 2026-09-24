"""Content metadata and prompt tests; no real planetary data or model inference."""

import pytest
from pydantic import ValidationError

from autonomous_modality.development_inputs import (
    ANSWER_POLICY,
    ANSWER_POLICY_VERSION,
    development_inventory,
)
from autonomous_modality.models import AssetContentInventory, InputDataModality
from autonomous_modality.pilot import CatalogueRow


def test_catalogue_inventory_matches_actual_schema() -> None:
    """No invented depth/age fields or case-specific values enter metadata."""
    inventory = development_inventory(InputDataModality.CRATER_CATALOG)
    assert set(inventory.available_fields) == set(CatalogueRow.model_fields)
    assert {"crater_depth", "absolute_age", "relative_age"} <= set(inventory.absent_fields)
    assert "Eminescu" not in inventory.model_dump_json()
    assert AssetContentInventory.model_validate_json(inventory.model_dump_json()) == inventory


@pytest.mark.parametrize(
    "modality",
    [
        InputDataModality.CRATER_CATALOG,
        InputDataModality.OPTICAL_IMAGE,
        InputDataModality.TOPOGRAPHY,
    ],
)
def test_inventories_are_fresh_and_explicit(modality: InputDataModality) -> None:
    inventory = development_inventory(modality)
    assert inventory.access_limits and inventory.model_inputs and inventory.absent_fields
    inventory.available_fields.append("TEST_MUTATION")
    assert "TEST_MUTATION" not in development_inventory(modality).available_fields


@pytest.mark.parametrize(
    "modality", [InputDataModality.SCIENTIFIC_LITERATURE, InputDataModality.SIMULATION_OUTPUT]
)
def test_unknown_package_content_is_not_invented(modality: InputDataModality) -> None:
    with pytest.raises(ValueError, match="No development-view inventory"):
        development_inventory(modality)


@pytest.mark.parametrize(
    "change",
    [
        {"available_fields": []},
        {"available_fields": ["name", "name"]},
        {"absent_fields": ["name"]},
        {"model_inputs": []},
        {"access_limits": []},
        {"invented_field": "value"},
    ],
)
def test_invalid_inventory(change: dict[str, object]) -> None:
    payload = development_inventory(InputDataModality.CRATER_CATALOG).model_dump()
    payload.update(change)
    with pytest.raises(ValidationError):
        AssetContentInventory.model_validate(payload)


def test_concise_policy_preserves_open_ended_richness() -> None:
    assert ANSWER_POLICY_VERSION == "english-ap-concise-1.0"
    assert "no required number of ideas" in ANSWER_POLICY
    assert "Merge overlapping ideas" in ANSWER_POLICY
    assert "end the answer immediately" in ANSWER_POLICY
    assert "proposed" in ANSWER_POLICY
    assert "200-300 words" in ANSWER_POLICY
