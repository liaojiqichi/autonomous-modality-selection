"""Synthetic fixtures only; no observed planetary data are present."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from autonomous_modality.iterative import (
    GenerationReply,
    IterativePolicy,
    answer_messages,
    run_iterative_selection,
)
from autonomous_modality.models import (
    AssetAvailability,
    CraterQuestionType,
    InputDataModality,
    InputSelectionRequest,
)
from autonomous_modality.multispectral import (
    MultispectralPackage,
    SpectralMetadata,
    main,
    multispectral_asset,
    multispectral_loader,
    summarize_multispectral,
)
from autonomous_modality.selection import select_baseline


def metadata() -> SpectralMetadata:
    return SpectralMetadata(
        case_id="fixture",
        product_id="fixture",
        source_uri="fixture://synthetic",
        instrument="MESSENGER_MDIS_WAC",
        quantity="radiance_factor_I_over_F",
        processing="calibrated_photometrically_corrected",
        calibration_reference="Test declaration",
        spatial_reference="Test grid",
        pixel_resolution_m=100,
        coverage_description="Synthetic grid",
        registration_limitations="No real registration",
        provenance_kind="synthetic_fixture",
        bands=[{"band_id": str(i), "wavelength_nm": w} for i, w in enumerate([430, 750, 1000])],
    )


def source_file(tmp_path: Path) -> Path:
    source = tmp_path / "fixture.npz"
    values = np.arange(12, dtype=float).reshape(3, 2, 2)
    values[1] = np.nan
    np.savez(source, reflectance=values, roi_sample=np.ones((2, 2), dtype=bool))
    return source


def test_summary_roundtrip(tmp_path: Path) -> None:
    package = summarize_multispectral(source_file(tmp_path), metadata())
    assert MultispectralPackage.model_validate_json(package.model_dump_json()) == package
    stats = package.regions[0].statistics
    assert stats[0].mean == 1.5
    assert stats[0].std == pytest.approx(np.sqrt(1.25))
    assert stats[0].count == 4
    assert stats[1].count == 0 and stats[1].mean is None
    assert (
        multispectral_asset(package, estimated_cost=2).availability == AssetAvailability.UNAVAILABLE
    )


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "RGB"},
        {"pixel_resolution_m": -1},
        {"processing": "uncalibrated"},
        {"unknown": 1},
        {"bands": [{"band_id": "same", "wavelength_nm": 430}] * 3},
        {
            "bands": [
                {"band_id": str(i), "wavelength_nm": w} for i, w in enumerate([750, 430, 1000])
            ]
        },
    ],
)
def test_invalid_metadata(change: dict) -> None:
    data = metadata().model_dump()
    data.update(change)
    with pytest.raises(ValidationError):
        SpectralMetadata.model_validate(data)


@pytest.mark.parametrize("kind", ["rgb", "shape", "empty", "mask_shape", "no_regions", "nan"])
def test_invalid_arrays(tmp_path: Path, kind: str) -> None:
    values = np.zeros((3, 2, 2), dtype=float)
    mask = np.ones((2, 2), dtype=bool)
    if kind == "rgb":
        values = values.astype(np.uint8)
    elif kind == "shape":
        values = values[0]
    elif kind == "empty":
        mask[:] = False
    elif kind == "mask_shape":
        mask = mask[:1]
    elif kind == "nan":
        values[:] = np.nan
    source = tmp_path / "invalid.npz"
    np.savez(source, reflectance=values, **({} if kind == "no_regions" else {"roi_a": mask}))
    with pytest.raises(ValueError):
        summarize_multispectral(source, metadata())


def test_synthetic_rejected(tmp_path: Path) -> None:
    source = source_file(tmp_path)
    package = summarize_multispectral(source, metadata())
    path = tmp_path / "package.json"
    path.write_text(package.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="SYNTHETIC_PACKAGE"):
        multispectral_loader(path, expected_case_id="fixture", source_path=source)


@pytest.mark.parametrize("mutation", ["none", "source", "package", "case", "modality"])
def test_integrity(tmp_path: Path, mutation: str) -> None:
    # Test the observed declaration branch; these bytes remain synthetic fixtures.
    source = source_file(tmp_path)
    declaration = metadata()
    declaration.provenance_kind = "observed"
    package = summarize_multispectral(source, declaration)
    path = tmp_path / "package.json"
    path.write_text(package.model_dump_json(), encoding="utf-8")
    if mutation == "case":
        with pytest.raises(ValueError, match="CASE_MISMATCH"):
            multispectral_loader(path, expected_case_id="other", source_path=source)
        return
    load = multispectral_loader(path, expected_case_id="fixture", source_path=source)
    if mutation == "source":
        source.write_bytes(b"changed")
    if mutation == "package":
        path.write_text("{}", encoding="utf-8")
    if mutation != "none":
        with pytest.raises(ValueError):
            load(
                InputDataModality.OPTICAL_IMAGE
                if mutation == "modality"
                else InputDataModality.MULTISPECTRAL_IMAGE
            )
    else:
        observation = load(InputDataModality.MULTISPECTRAL_IMAGE)
        assert observation.evidence_sha256["numeric_source"] == package.source_sha256
        assert "wavelength_nm" in observation.blocks[0].text


@pytest.mark.parametrize("question_type", list(CraterQuestionType))
def test_selection_supports_multispectral(
    tmp_path: Path,
    selection_request: InputSelectionRequest,
    question_type: CraterQuestionType,
) -> None:
    declaration = metadata()
    declaration.provenance_kind = "observed"  # Test declaration only.
    package = summarize_multispectral(source_file(tmp_path), declaration)
    core_asset = next(
        a for a in selection_request.assets if a.modality == InputDataModality.OPTICAL_IMAGE
    )
    selection_request.assets = [multispectral_asset(package, estimated_cost=2)]
    if question_type == CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY:
        selection_request.assets.append(core_asset)
    selection_request.question.question_type = question_type
    selection_request.constraints.required_modalities = {InputDataModality.MULTISPECTRAL_IMAGE}
    decision = select_baseline(selection_request).decision
    assert InputDataModality.MULTISPECTRAL_IMAGE in [item.modality for item in decision.selected]


def test_iterative_acquisition_reaches_answer(
    tmp_path: Path,
    selection_request: InputSelectionRequest,
) -> None:
    declaration = metadata()
    declaration.provenance_kind = "observed"  # Test declaration only.
    source = source_file(tmp_path)
    package = summarize_multispectral(source, declaration)
    path = tmp_path / "package.json"
    path.write_text(package.model_dump_json(), encoding="utf-8")
    selection_request.assets = [multispectral_asset(package, estimated_cost=2)]
    selection_request.constraints.maximum_modalities = 2
    selection_request.constraints.maximum_total_cost = 4
    replies = iter(
        [
            {
                "action": "REQUEST_MODALITY",
                "modality": "MULTISPECTRAL_IMAGE",
                "reason": "PRIVATE_REASON",
            },
            {"action": "FINISH", "reason": "PRIVATE_REASON"},
        ]
    )

    def generate(messages: list[dict[str, object]], max_new_tokens: int) -> GenerationReply:
        return GenerationReply(text=json.dumps(next(replies)), finish_reason="eos")

    trace = run_iterative_selection(
        selection_request,
        IterativePolicy(cost_unit="legacy_ordinal_units", cost_definition="Test cost 2."),
        generate,
        multispectral_loader(path, expected_case_id="fixture", source_path=source),
        model_id="scripted-fixture",
        execution_kind="test",
    )
    assert trace.status == "ready"
    assert trace.cumulative_cost == 2
    prompt = json.dumps(answer_messages(trace, "Shared answer requirements"))
    assert "wavelength_nm" in prompt and "PRIVATE_REASON" not in prompt


def test_cli_refuses_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = source_file(tmp_path)
    meta = tmp_path / "metadata.json"
    meta.write_text(metadata().model_dump_json(), encoding="utf-8")
    output = tmp_path / "summary.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "multispectral",
            "--source",
            str(source),
            "--metadata",
            str(meta),
            "--output",
            str(output),
        ],
    )
    main()
    assert (
        MultispectralPackage.model_validate_json(output.read_bytes()).metadata.case_id == "fixture"
    )
    with pytest.raises(FileExistsError):
        main()
