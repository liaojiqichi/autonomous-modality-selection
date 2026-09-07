"""Offline QA and packaging tests use invented rasters, never observed planetary data."""
# Optional libraries must be checked before importing preparation modules.
# ruff: noqa: E402

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")
pytest.importorskip("matplotlib")

from rasterio.crs import CRS
from rasterio.transform import from_origin

from autonomous_modality.acquisition import DownloadRecord, SourceSpec, sha256_file
from autonomous_modality.benchmark import (
    CaseAudit,
    InputPackage,
    PreparedTask,
    QuestionSet,
    ReviewSet,
    VisualReview,
    audit_case,
    build_package,
    local_file,
    prepare_task,
    save_model,
    selected_evidence,
    verify_package,
)
from autonomous_modality.models import (
    AssetAvailability,
    InputDataModality,
    InputSelectionConstraints,
)
from autonomous_modality.pilot import CatalogueRow, PilotCase, PilotConfig, make_case
from autonomous_modality.selection import select_baseline


@pytest.fixture
def prepared_case(tmp_path: Path) -> tuple[PilotCase, Path, list[DownloadRecord], VisualReview]:
    """Prepare a small invented varying field to exercise the complete local adapter."""
    path = tmp_path / "synthetic.tif"
    crs = CRS.from_wkt(
        'PROJCS["Equirectangular Mercury",GEOGCS["GCS_Mercury",'
        'DATUM["D_Mercury",SPHEROID["Mercury",2439400,0]],PRIMEM["Reference_Meridian",0],'
        'UNIT["degree",0.0174532925199433]],PROJECTION["Equirectangular"],'
        'PARAMETER["standard_parallel_1",0],PARAMETER["central_meridian",30],'
        'PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1]]'
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=300,
        height=300,
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(-150000, 150000, 1000, 1000),
        nodata=-32768,
    ) as output:
        output.write(np.indices((300, 300)).sum(axis=0).astype("float32") / 3 + 1, 1)
    sources = [
        DownloadRecord(
            source=SourceSpec(
                source_id=identifier,
                url="https://example.org/synthetic.tif",
                filename=path.name,
                expected_bytes=path.stat().st_size,
                format="tiff",
                citation="Invented offline fixture; not scientific data",
            ),
            retrieved_utc=datetime.now(UTC),
            path=str(path),
            bytes=path.stat().st_size,
            sha256=sha256_file(path),
        )
        for identifier in ("herrick-2011-catalog", "mdis-loi-v1", "usgs-dem-v2")
    ]
    row = CatalogueRow(
        id=1,
        lat_n=0,
        lon_e_0=30,
        int_shp="",
        rim_shp="",
        cent_struc="",
        rayed="",
        name="Synthetic fixture",
        diameter=50,
    )
    root = tmp_path / "run"
    root.mkdir()
    case = make_case(
        row, {s.source.source_id: s for s in sources}, root, PilotConfig(sample_count=1)
    )
    save_model(root / "crater-1" / "case.json", case)
    review = VisualReview(
        case_id=1,
        status="provisional_pass",
        observation="Synthetic test only",
        concern="No real visual review is claimed for this invented fixture",
        reviewer="Codex visual screening; not a planetary-science expert",
        evidence_files=["overview.png", "dem_local.png"],
    )
    return case, root, sources, review


def test_audit_package_relocation_and_no_modality_leakage(
    prepared_case: tuple[PilotCase, Path, list[DownloadRecord], VisualReview],
    tmp_path: Path,
) -> None:
    case, root, sources, review = prepared_case
    audit = audit_case(case, root, review, sources)
    assert audit.status == "provisional_pass", audit.technical_errors
    destination = tmp_path / "bundle"
    package = build_package(case, audit, root, destination)
    assert len(package.files) == 8
    assert all("overview" not in f.path for f in package.files)
    assert all(a.quality_score is None for a in package.assets)
    assert package.expert_approved is False
    moved = tmp_path / "relocated"
    shutil.copytree(destination, moved)
    assert verify_package(moved) == package
    questions = QuestionSet.model_validate_json(
        Path("configs/mercury_questions_v1.json").read_text(encoding="utf-8")
    )
    for question in questions.questions:
        for budget in (3, 5):
            task = prepare_task(package, question, budget)
            assert task.result.decision.total_cost <= budget
            assert "{crater}" not in task.request.question.text
            assert task.llm_called is False
            assert {f.modality for f in task.selected_files} == {
                selected.modality for selected in task.result.decision.selected
            }
    request = task.request.model_copy(deep=True)
    request.question.question_type = "GENERAL_CRATER_INVESTIGATION"
    for modality in (InputDataModality.OPTICAL_IMAGE, InputDataModality.TOPOGRAPHY):
        request.constraints = InputSelectionConstraints(
            maximum_modalities=1, required_modalities={modality}
        )
        result = select_baseline(request)
        files = selected_evidence(package, result)
        assert files and all(f.modality == modality for f in files)
        if modality == InputDataModality.OPTICAL_IMAGE:
            assert all("profile" not in f.path and "dem" not in f.path for f in files)
        result.decision.selected[0].asset_id = "other-case"
        with pytest.raises(ValueError, match="does not belong"):
            selected_evidence(package, result)
    with pytest.raises(FileExistsError):
        build_package(case, audit, root, destination)
    local_file(moved, package.files[0].path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        verify_package(moved)
    payload = package.model_dump()
    payload["files"].append(payload["files"][0])
    with pytest.raises(ValidationError, match="duplicate evidence"):
        InputPackage.model_validate(payload)


def test_fixed_control_and_scientific_question_readiness(
    prepared_case: tuple[PilotCase, Path, list[DownloadRecord], VisualReview],
    tmp_path: Path,
) -> None:
    case, root, sources, review = prepared_case
    package = build_package(
        case, audit_case(case, root, review, sources), root, tmp_path / "bundle"
    )
    questions = QuestionSet.model_validate_json(
        Path("configs/mercury_questions_v2.json").read_text(encoding="utf-8")
    )
    original = package.model_dump_json()
    assert len(questions.questions) == 7
    old = QuestionSet.model_validate_json(
        Path("configs/mercury_questions_v1.json").read_text(encoding="utf-8")
    )
    assert questions.questions[:4] == old.questions
    for question in questions.questions:
        for budget in (3, 4, 5):
            task = prepare_task(
                package,
                question,
                budget,
                fixed_image_topography=budget == 4,
                question_version=questions.version,
            )
            assert task.question_version == questions.version
            assert task.request.question.crater.diameter_km is None
            assert PreparedTask.model_validate_json(task.model_dump_json()) == task
            if budget == 4:
                assert task.condition == "fixed-image-topography"
                assert {f.modality for f in task.selected_files} == {
                    InputDataModality.OPTICAL_IMAGE,
                    InputDataModality.TOPOGRAPHY,
                }
                assert len(task.selected_files) == 7
                assert task.result.decision.total_cost == 4
                assert all(
                    "catalogue" not in f.path and "overview" not in f.path
                    for f in task.selected_files
                )
                payload = task.model_dump()
                payload["selected_files"].append(package.files[0].model_dump())
                with pytest.raises(ValidationError, match="modalities differ"):
                    PreparedTask.model_validate(payload)
            if question.question_id in {"Q5", "Q6", "Q7"}:
                assert task.quantitative_status == "not_ready"
                assert InputDataModality.SIMULATION_OUTPUT in task.missing_quantitative_modalities
                assert task.unverified_quantitative_prerequisites
                with pytest.raises(ValidationError, match="readiness"):
                    PreparedTask.model_validate(
                        {**task.model_dump(), "quantitative_status": "not_assessed"}
                    )
    assert package.model_dump_json() == original
    with pytest.raises(ValueError, match="budget 4"):
        prepare_task(package, questions.questions[0], 3, fixed_image_topography=True)
    for asset in package.assets:
        if asset.modality == InputDataModality.TOPOGRAPHY:
            asset.availability = AssetAvailability.UNAVAILABLE
    with pytest.raises(ValueError, match="required modalities"):
        prepare_task(package, questions.questions[0], 4, fixed_image_topography=True)


@pytest.mark.parametrize("fault", ["raster", "profile", "missing", "lineage", "held", "unreviewed"])
def test_audit_rejects_bad_evidence_and_preserves_holds(
    prepared_case: tuple[PilotCase, Path, list[DownloadRecord], VisualReview],
    tmp_path: Path,
    fault: str,
) -> None:
    case, root, sources, review = prepared_case
    if fault == "raster":
        with rasterio.open(root / "crater-1" / "dem_local.tif", "r+") as dataset:
            dataset.write(np.zeros((dataset.height, dataset.width), dtype="float32"), 1)
    elif fault == "profile":
        path = root / "crater-1" / "east_west_profile.csv"
        path.write_text("east_from_catalogue_centre_km,elevation_m\n0,123\n")
    elif fault == "missing":
        # Remove only a disposable test fixture, not a scientific source.
        (root / "crater-1" / "image_local.png").unlink()
    elif fault == "lineage":
        sources = []
    elif fault == "held":
        review.status = "hold"
    else:
        review.evidence_files = ["overview.png", "image_local.png"]
    audit = audit_case(case, root, review, sources)
    assert audit.status == ("hold" if fault == "held" else "reject")
    with pytest.raises(ValueError, match="approved"):
        build_package(case, audit, root, tmp_path / "bundle")
    with pytest.raises(ValidationError, match="inconsistent"):
        CaseAudit.model_validate({**audit.model_dump(), "status": "provisional_pass"})


@pytest.mark.parametrize(
    "path", ["../outside.txt", "/outside.txt", "C:/outside.txt", "..\\outside", "missing"]
)
def test_safe_package_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError):
        local_file(tmp_path, path)


def test_frozen_configs_are_strict_and_cover_twelve_distinct_cases() -> None:
    payload = json.loads(Path("configs/mercury_visual_reviews_v1.json").read_text(encoding="utf-8"))
    reviews = ReviewSet.model_validate(payload)
    assert len(reviews.reviews) == 12
    assert sum(r.status == "provisional_pass" for r in reviews.reviews) == 7
    payload["reviews"].append(payload["reviews"][0])
    with pytest.raises(ValidationError, match="duplicate"):
        ReviewSet.model_validate(payload)
    questions = json.loads(Path("configs/mercury_questions_v1.json").read_text(encoding="utf-8"))
    assert len(QuestionSet.model_validate(questions).questions) == 4
    questions["questions"][1] = questions["questions"][0]
    with pytest.raises(ValidationError, match="duplicate"):
        QuestionSet.model_validate(questions)


def test_four_condition_cli_and_evidence_isolation(
    prepared_case: tuple[PilotCase, Path, list[DownloadRecord], VisualReview],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autonomous_modality.experiments import main

    case, root, sources, review = prepared_case
    destination = tmp_path / "packages" / "crater-1"
    build_package(case, audit_case(case, root, review, sources), root, destination)
    output = tmp_path / "primary"
    monkeypatch.setattr(
        "sys.argv", ["experiments", "--benchmark", str(destination.parent), "--output", str(output)]
    )
    main()
    run = json.loads((output / "preparation.json").read_text(encoding="utf-8"))
    assert len(run["records"]) == 16
    assert run["answers_generated"] == 0
    from autonomous_modality.experiments import PreparationRun

    assert PreparationRun.model_validate(run).answers_generated == 0
    invalid = json.loads(json.dumps(run))
    invalid["records"][0]["answer_input"]["evidence_paths"] = ["unselected.txt"]
    with pytest.raises(ValidationError, match="paths mismatch"):
        PreparationRun.model_validate(invalid)
    for row in run["records"]:
        condition = row["selection"]["condition"]
        if condition == "AGENT":
            assert row["answer_input"] is None
            assert row["selection"]["status"] == "pending_agent"
        else:
            answer = row["answer_input"]
            assert set(answer) == {"question", "answer_requirements", "evidence_paths"}
            assert answer["question"]["crater"]["diameter_km"] is None
            assert all("overview" not in p for p in answer["evidence_paths"])
            if condition == "NO_DATA":
                assert answer["evidence_paths"] == [] and row["evidence"] == []
    with pytest.raises(ValueError, match="new directory"):
        main()
    monkeypatch.setattr(
        "sys.argv",
        [
            "experiments",
            "--benchmark",
            str(destination.parent),
            "--questions",
            "configs/mercury_questions_v2.json",
            "--output",
            str(tmp_path / "rejected"),
        ],
    )
    with pytest.raises(ValueError, match="outside the active protocol"):
        main()
    assert not (tmp_path / "rejected").exists()
