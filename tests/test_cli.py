"""End-to-end CLI test for the revised input-selection prototype."""

import json

import pytest

from autonomous_modality.cli import (
    CASE_SPECIFIC_NOTICE,
    METADATA_ONLY_NOTICE,
    main,
    mercury_demo_assets,
)
from autonomous_modality.models import (
    AssetAvailability,
    DataAssetProfile,
    InputDataModality,
    InputSelectionRequest,
)
from autonomous_modality.selection import filter_candidates


def test_cli_emits_input_selection_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "--question",
            "How could the formation of Caloris be investigated?",
            "--question-type",
            "EXPLANATORY_PERSPECTIVE_EXPLORATION",
            "--crater-name",
            "Caloris",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["decision"]["selected"]
    assert "expected_richness" in payload["decision"]
    assert payload["rule_version"] == "input-richness-baseline-1.2"
    emitted_assets = payload["candidates"]["available_assets"]
    for asset in emitted_assets:
        assert METADATA_ONLY_NOTICE in asset["limitations"]
        assert asset["source_uri"] is None
        assert asset["quality_score"] is None
        if asset["availability"] == "CASE_SPECIFIC":
            assert CASE_SPECIFIC_NOTICE in asset["limitations"]
    assert {item["asset_id"] for item in payload["decision"]["selected"]}.issubset(
        asset["asset_id"] for asset in emitted_assets
    )


@pytest.mark.parametrize("modality", list(InputDataModality))
def test_every_demo_asset_preserves_its_metadata_only_notice_on_export(
    modality: InputDataModality,
) -> None:
    asset = next(item for item in mercury_demo_assets() if item.modality is modality)

    restored = DataAssetProfile.model_validate_json(asset.model_dump_json())

    assert METADATA_ONLY_NOTICE in restored.limitations
    assert restored.source_uri is None
    assert restored.quality_score is None
    assert restored.schema_version == "2.0"
    if restored.availability is AssetAvailability.CASE_SPECIFIC:
        assert CASE_SPECIFIC_NOTICE in restored.limitations


def test_demo_rejects_unknown_crater_instead_of_using_caloris_coordinates() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--question", "Investigate this crater", "--crater-name", "Eminescu"])
    assert exc.value.code == 2


def test_demo_availability_and_existing_limitations_remain_unchanged(
    selection_request: InputSelectionRequest,
) -> None:
    assets = {asset.modality: asset for asset in mercury_demo_assets()}
    assert assets[InputDataModality.OPTICAL_IMAGE].availability is AssetAvailability.AVAILABLE
    assert assets[InputDataModality.CRATER_CATALOG].availability is AssetAvailability.AVAILABLE
    assert assets[InputDataModality.TOPOGRAPHY].availability is AssetAvailability.CASE_SPECIFIC
    assert (
        assets[InputDataModality.SCIENTIFIC_LITERATURE].availability
        is AssetAvailability.CASE_SPECIFIC
    )
    assert assets[InputDataModality.SIMULATION_OUTPUT].availability is AssetAvailability.UNAVAILABLE
    assert (
        "single-band 8-bit stretched reflectance"
        in assets[InputDataModality.OPTICAL_IMAGE].limitations
    )
    assert (
        "morphology descriptors have limited reliability"
        in assets[InputDataModality.CRATER_CATALOG].limitations
    )
    assert (
        "no concrete simulation asset has been acquired"
        in assets[InputDataModality.SIMULATION_OUTPUT].limitations
    )
    assert {asset.modality for asset in filter_candidates(selection_request).available_assets} == {
        InputDataModality.OPTICAL_IMAGE,
        InputDataModality.CRATER_CATALOG,
        InputDataModality.TOPOGRAPHY,
        InputDataModality.SCIENTIFIC_LITERATURE,
    }
