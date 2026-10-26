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


def test_frozen_inventory_not_changed() -> None:
    before = development_inventory(InputDataModality.OPTICAL_IMAGE)
    modality_inventory("OPTICAL_IMAGE")
    assert development_inventory(InputDataModality.OPTICAL_IMAGE) == before
    assert before.version == "mercury-development-contents-1.1"


def test_reviewer_amendment_keeps_baseline_configuration() -> None:
    assets = {
        name: {
            "cost": 1 if name == "CRATER_CATALOG" else 2,
            "description": "fixture",
            "content_inventory": None,
        }
        for name in NAMES
    }
    ns = {
        "ASSETS": assets,
        "CONFIG": {"assets": copy.deepcopy(assets)},
        "CASE_ID": "1",
        "CASE_NAME": "Fixture",
        "MAX_MODALITIES": 2,
        "BUDGET": 4,
    }
    before = copy.deepcopy(ns)
    assert reviewer_assets(ns) is assets
    ns["REVISION_ASSET_DESCRIPTION_VERSION"] = ASSET_DESCRIPTION_VERSION
    request = build_revision_request(
        ns,
        {
            "question_id": "Q1",
            "text": "Check {crater}",
            "question_type": "ANALYTICAL_APPROACH_DISCOVERY",
            "answer_requirements": ["Compare"],
        },
    )
    assert ns["ASSETS"] == before["ASSETS"] and ns["CONFIG"] == before["CONFIG"]
    assert all(a.content_inventory.version == ASSET_DESCRIPTION_VERSION for a in request.assets)
    assert request.constraints.maximum_total_cost == 4
    assert {a.modality.value: a.estimated_cost for a in request.assets} == {
        name: assets[name]["cost"] for name in NAMES
    }
    assert "Supported analyses:" in request.assets[0].limitations[0]
    ns["REVISION_ASSET_DESCRIPTION_VERSION"] = "unknown"
    with pytest.raises(ValueError, match="UNKNOWN_REVISION_ASSET_DESCRIPTION_VERSION"):
        reviewer_assets(ns)
