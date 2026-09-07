"""Small synthetic fixtures test adapters; no planetary downloads in unit tests."""
# Optional dependency checks must run before importing the pilot adapter.
# ruff: noqa: E402

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

np = pytest.importorskip("numpy", reason="install the optional pilot dependencies")
rasterio = pytest.importorskip("rasterio", reason="install the optional pilot dependencies")
pytest.importorskip("matplotlib", reason="install the optional pilot dependencies")

from rasterio.crs import CRS
from rasterio.transform import from_origin

from autonomous_modality.acquisition import DownloadRecord, SourceSpec, sha256_file
from autonomous_modality.models import AssetAvailability, InputDataModality, InputSelectionRequest
from autonomous_modality.pilot import (
    CatalogueRow,
    PilotCase,
    PilotConfig,
    PilotRun,
    SelectionTrial,
    choose_targets,
    crop_product,
    load_catalogue,
    run_trials,
    scaled_dem,
    write_report,
)


def fixture_row(identifier: int = 1) -> CatalogueRow:
    """Return an invented crater record used only in offline tests."""
    return CatalogueRow(
        id=identifier,
        lat_n=0,
        lon_e_0=30,
        int_shp="ff",
        rim_shp="t",
        cent_struc="n",
        rayed="n",
        name="Synthetic fixture",
        diameter=50,
    )


def test_catalogue_validation_and_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "fixture.csv"
    row = fixture_row()
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row.model_dump()))
        writer.writeheader()
        writer.writerow(row.model_dump())
    assert load_catalogue(path) == [row]
    with path.open("a", newline="", encoding="utf-8") as stream:
        csv.DictWriter(stream, fieldnames=list(row.model_dump())).writerow(row.model_dump())
    with pytest.raises(ValueError, match="duplicate"):
        load_catalogue(path)


def test_catalogue_rejects_duplicate_column_names(tmp_path: Path) -> None:
    path = tmp_path / "fixture.csv"
    fields = [*CatalogueRow.model_fields, "diameter"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerow([*fixture_row().model_dump().values(), 100])
    with pytest.raises(ValueError, match="columns"):
        load_catalogue(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("lat_n", 91), ("diameter", 0), ("diameter", float("nan")), ("lon_e_0", 361)],
)
def test_invalid_catalogue_numbers(field: str, value: float) -> None:
    payload = fixture_row().model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        CatalogueRow.model_validate(payload)


def test_sampling_is_deterministic_and_filters_seams() -> None:
    rows = [fixture_row(i) for i in range(1, 7)]
    rows[-1].lon_e_0 = 179
    config = PilotConfig(sample_count=3)
    selected, count = choose_targets(rows, config)
    assert count == 5
    assert [r.id for r in selected] == [1, 3, 5]
    assert choose_targets(list(reversed(rows)), config)[0] == selected
    with pytest.raises(ValueError, match="too few"):
        choose_targets(rows, PilotConfig(sample_count=6))


def test_dem_scale_masks_nodata_before_conversion() -> None:
    values = np.ma.array([[100, -32768], [200, 300]], mask=[[False, True], [False, False]])
    actual = scaled_dem(values, 0.5, 10)
    np.testing.assert_allclose(actual, [[60, np.nan], [110, 160]], equal_nan=True)
    with pytest.raises(ValueError):
        scaled_dem(values, -1, 0)


def test_trial_matrix_retains_inputs_and_respects_ablation_constraints(
    selection_request: InputSelectionRequest,
    tmp_path: Path,
) -> None:
    case = PilotCase(
        catalogue=fixture_row(),
        products=[],
        assets=[
            asset
            for asset in selection_request.assets
            if asset.modality
            in {
                InputDataModality.CRATER_CATALOG,
                InputDataModality.OPTICAL_IMAGE,
                InputDataModality.TOPOGRAPHY,
            }
        ],
        accepted=True,
        limitations=["Synthetic test fixture, not scientific data."],
        profile_path="synthetic-fixture-only",
        overview_path="synthetic-fixture-only",
    )
    original = case.model_dump_json()
    trials = run_trials(case)
    assert len(trials) == 16
    assert len({(trial.condition, trial.request.question.question_type) for trial in trials}) == 16
    for trial in trials:
        selected = {item.modality for item in trial.result.decision.selected}
        assert not selected & trial.request.constraints.forbidden_modalities
        assert trial.result.decision.total_cost <= trial.request.constraints.maximum_total_cost
        assert trial.request.question.crater.crater_id == str(case.catalogue.id)
    assert case.model_dump_json() == original
    for asset in case.assets:
        asset.availability = AssetAvailability.UNAVAILABLE
    case.accepted = False
    failed = run_trials(case)
    assert len(failed) == 16
    assert all(trial.result is None and trial.error for trial in failed)
    with pytest.raises(ValidationError, match="exactly one"):
        SelectionTrial.model_validate({**failed[0].model_dump(), "error": None})
    with pytest.raises(ValidationError, match="exactly one"):
        SelectionTrial.model_validate({**trials[0].model_dump(), "error": "conflicting"})
    run = PilotRun(
        schema_version="pilot-run-1.0",
        run_id="synthetic-fixture",
        created_utc=datetime.now(UTC),
        config=PilotConfig(version="mercury-real-pilot-1.0"),
        code_sha256={},
        environment={},
        sources=[],
        catalogue_rows=1,
        eligible_rows=1,
        sampling="Synthetic fixture",
        cases=[],
        trials=trials + failed,
        limitations=[],
    )
    assert PilotRun.model_validate_json(run.model_dump_json()) == run
    write_report(run, tmp_path)
    report = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "mercury-real-pilot-1.0" in report
    assert "32" in report and "16" in report


@pytest.mark.parametrize("topography", [True, False])
def test_real_adapter_on_synthetic_tiff_preserves_scale_and_crs(
    tmp_path: Path,
    topography: bool,
) -> None:
    # A constant synthetic Mercury grid; no real observation is used by this test.
    crs = CRS.from_wkt(
        'PROJCS["Equirectangular Mercury",GEOGCS["GCS_Mercury",'
        'DATUM["D_Mercury",SPHEROID["Mercury",2439400,0]],PRIMEM["Reference_Meridian",0],'
        'UNIT["degree",0.0174532925199433]],PROJECTION["Equirectangular"],'
        'PARAMETER["standard_parallel_1",0],PARAMETER["central_meridian",30],'
        'PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1]]'
    )
    path = tmp_path / "synthetic.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=300,
        height=300,
        count=1,
        dtype="int16",
        crs=crs,
        transform=from_origin(-150000, 150000, 1000, 1000),
        nodata=-32768,
    ) as output:
        output.write(np.full((300, 300), 100, dtype="int16"), 1)
        output.scales = (0.5,)
        output.offsets = (10,)
    checksum = sha256_file(path)
    record = DownloadRecord(
        source=SourceSpec(
            source_id="synthetic",
            url="https://example.org/fixture.tif",
            filename=path.name,
            expected_bytes=path.stat().st_size,
            format="tiff",
            citation="Synthetic fixture",
        ),
        retrieved_utc=datetime.now(UTC),
        path=str(path),
        bytes=path.stat().st_size,
        sha256=checksum,
    )
    product, array = crop_product(
        path, record, fixture_row(), 2, tmp_path / "derived.tif", topography
    )
    np.testing.assert_allclose(array, 60 if topography else 100, atol=0.001)
    assert product.valid_fraction == 1
    assert product.source_scale == 0.5
    assert product.source_offset == 10
    assert sha256_file(path) == checksum
    with rasterio.open(product.data_path) as derived:
        assert derived.scales == (1.0,)
        assert "Azimuthal_Equidistant" in derived.crs.to_wkt()
    with pytest.raises(FileExistsError):
        crop_product(path, record, fixture_row(), 2, tmp_path / "derived.tif", topography)
    with pytest.raises(ValueError, match="two or five"):
        crop_product(path, record, fixture_row(), 3, tmp_path / "bad.tif", topography)
    distant = fixture_row()
    distant.lat_n = 80
    with pytest.raises(ValueError, match="boundary"):
        crop_product(path, record, distant, 2, tmp_path / "outside.tif", topography)
    with pytest.raises(ValueError, match="raw"):
        crop_product(path, record, fixture_row(), 2, tmp_path / "raw" / "bad.tif", topography)
    with rasterio.open(path, "r+") as output:
        output.transform = from_origin(-150000, 150000, 1000, 2000)
    with pytest.raises(ValueError, match="square pixels"):
        crop_product(path, record, fixture_row(), 2, tmp_path / "bad-grid.tif", topography)
    with rasterio.open(path, "r+") as output:
        output.crs = CRS.from_wkt(
            'GEOGCS["GCS_Mercury",DATUM["D_Mercury",SPHEROID["Mercury",2439400,0]],'
            'PRIMEM["Reference_Meridian",0],UNIT["degree",0.0174532925199433]]'
        )
    with pytest.raises(ValueError, match="projected in metres"):
        crop_product(path, record, fixture_row(), 2, tmp_path / "bad-crs.tif", topography)
