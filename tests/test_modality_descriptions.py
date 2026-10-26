"""Offline tests for versioned, representation-specific modality descriptions."""

import copy
import json

import pytest

from autonomous_modality.development_inputs import development_inventory
from autonomous_modality.modality_descriptions import (
    ASSET_DESCRIPTION_VERSION,
    describe_assets,
    modality_description,
    modality_inventory,
)
from autonomous_modality.models import AssetContentInventory, InputDataModality
from autonomous_modality.revision_colab import build_revision_request, reviewer_assets

NAMES = ("CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY", "MULTISPECTRAL_IMAGE")


@pytest.mark.parametrize("name", NAMES)
def test_uniform_sections_and_json_roundtrip(name: str) -> None:
    description = modality_description(name)
    assert set(description.model_dump()) == {
        "contents",
        "coverage",
        "supported_analyses",
        "interpretation_limits",
    }
    inventory = modality_inventory(name)
    assert inventory.version == ASSET_DESCRIPTION_VERSION
    assert AssetContentInventory.model_validate_json(inventory.model_dump_json()) == inventory
    assert "Supported analyses:" in description.text()
    assert "Interpretation limits:" in description.text()


def test_copy_preserves_costs_and_evidence_metadata() -> None:
    original = {
        name: {
            "cost": 1 if name == "CRATER_CATALOG" else 2,
            "path": f"fixture/{name}",
            "description": "old",
            "content_inventory": {"version": "fixture"},
        }
        for name in NAMES
    }
    before = copy.deepcopy(original)
    revised = describe_assets(original)
    assert original == before
    for name in NAMES:
        assert revised[name]["cost"] == original[name]["cost"]
        assert revised[name]["path"] == original[name]["path"]
    revised["OPTICAL_IMAGE"]["content_inventory"]["available_fields"].clear()
    assert modality_inventory("OPTICAL_IMAGE").available_fields
    json.dumps(revised, allow_nan=False)


@pytest.mark.parametrize("name", ["UNKNOWN", "SCIENTIFIC_LITERATURE", "SIMULATION_OUTPUT"])
def test_unsupported_modalities(name: str) -> None:
    with pytest.raises(ValueError):
        describe_assets({name: {"cost": 2}})


def test_empty_assets_rejected() -> None:
    with pytest.raises(ValueError):
        describe_assets({})


def test_actual_spectral_granularity_and_uncertainty() -> None:
    text = modality_description("MULTISPECTRAL_IMAGE").text()
    assert "eight MDIS bands" in text and "Four geometric regions" in text
    assert "0 <= r < 0.25D" in text and "D <= r < 2D" in text
    assert "Spatial standard deviation is not measurement uncertainty" in text
    assert "16 spectral" not in str(modality_inventory("MULTISPECTRAL_IMAGE").model_dump())


def test_compatibility_inventory_uses_current_description() -> None:
    before = development_inventory(InputDataModality.OPTICAL_IMAGE)
    assert before == modality_inventory("OPTICAL_IMAGE")
    assert before.version == ASSET_DESCRIPTION_VERSION
    before.available_fields.clear()
    assert development_inventory(InputDataModality.OPTICAL_IMAGE).available_fields


def test_reviewer_uses_identical_current_assets() -> None:
    assets = describe_assets(
        {name: {"cost": 1 if name == "CRATER_CATALOG" else 2} for name in NAMES}
    )
    ns = {
        "ASSETS": assets,
        "CONFIG": {
            "assets": copy.deepcopy(assets),
            "inventory_version": ASSET_DESCRIPTION_VERSION,
            "asset_description_version": ASSET_DESCRIPTION_VERSION,
            "asset_description_scope": "all_selectors",
        },
        "CASE_ID": "1",
        "CASE_NAME": "Fixture",
        "MAX_MODALITIES": 2,
        "BUDGET": 4,
    }
    before = copy.deepcopy(ns)
    request = build_revision_request(
        ns,
        {
            "question_id": "Q1",
            "text": "Check {crater}",
            "question_type": "ANALYTICAL_APPROACH_DISCOVERY",
            "answer_requirements": ["Compare"],
        },
    )
    assert ns == before
    for a in request.assets:
        assert a.limitations == [assets[a.modality.value]["description"]]
        assert (
            a.content_inventory.model_dump(mode="json")
            == assets[a.modality.value]["content_inventory"]
        )
    assert reviewer_assets(ns) == assets


@pytest.mark.parametrize(
    "field,value",
    [
        ("asset_description_version", "old"),
        ("inventory_version", "old"),
        ("assets", {}),
        ("asset_description_scope", "reviewer_only"),
    ],
)
def test_reviewer_rejects_mixed_configuration(field: str, value: object) -> None:
    assets = describe_assets({"OPTICAL_IMAGE": {"cost": 2}})
    config = {
        "assets": assets,
        "inventory_version": ASSET_DESCRIPTION_VERSION,
        "asset_description_version": ASSET_DESCRIPTION_VERSION,
        "asset_description_scope": "all_selectors",
    }
    config[field] = value
    with pytest.raises(ValueError, match="MIXED_ASSET_DESCRIPTIONS"):
        reviewer_assets({"ASSETS": assets, "CONFIG": config})


def test_reviewer_does_not_silently_upgrade_old_assets() -> None:
    with pytest.raises(ValueError, match="ASSET_DESCRIPTIONS_OUTDATED"):
        reviewer_assets(
            {"ASSETS": {"OPTICAL_IMAGE": {"cost": 2, "description": "old"}}, "CONFIG": {}}
        )
