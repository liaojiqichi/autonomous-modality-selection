"""Synthetic fixtures only: no real planetary data, network, or inference."""

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from ams_evidence_views.adapter import build_content, load_package
from ams_evidence_views.builder import build_package, centre_profile, read_grid, terrain_summary
from ams_evidence_views.models import Settings
from pydantic import ValidationError
from rasterio.transform import from_origin

from autonomous_modality.acquisition import sha256_file


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """Create an explicitly synthetic compatible legacy package."""
    root = tmp_path / "synthetic_source"
    (root / "evidence").mkdir(parents=True)
    case = dict(
        id=1,
        name="SYNTHETIC_NOT_OBSERVED",
        lat_n=0.0,
        lon_e_0=0.0,
        diameter=10.0,
        int_shp="x",
        rim_shp="x",
        cent_struc="x",
        rayed="n",
    )
    (root / "evidence/catalogue.json").write_text(json.dumps(case), encoding="utf-8")
    specs = [
        ("catalogue.json", "CRATER_CATALOG", "catalogue_record"),
        ("image_local.tif", "OPTICAL_IMAGE", "numeric_raster"),
        ("image_context.tif", "OPTICAL_IMAGE", "numeric_raster"),
        ("dem_local.tif", "TOPOGRAPHY", "numeric_raster"),
    ]
    for name, _, _ in specs[1:]:
        with rasterio.open(
            root / "evidence" / name,
            "w",
            driver="GTiff",
            width=6,
            height=6,
            count=1,
            dtype="float32",
            nodata=-9999,
            crs="+proj=aeqd +lat_0=0 +lon_0=0 +R=2439400 +units=m",
            transform=from_origin(-3000, 3000, 1000, 1000),
        ) as ds:
            ds.write(np.arange(36, dtype="float32").reshape(6, 6), 1)
    files = [
        dict(
            path="evidence/" + n,
            modality=m,
            representation=r,
            sha256=sha256_file(root / "evidence" / n),
            bytes=(root / "evidence" / n).stat().st_size,
            units="metres (synthetic)",
            source_id="synthetic",
            parent_paths=[],
        )
        for n, m, r in specs
    ]
    assets = [
        dict(
            asset_id=m,
            modality=m,
            title="synthetic fixture",
            availability="AVAILABLE",
            source_uri="evidence/" + n,
            data_format="fixture",
            estimated_cost=1.0,
        )
        for n, m, _ in [specs[0], specs[1], specs[3]]
    ]
    package = dict(
        case=case,
        assets=assets,
        files=files,
        source_hashes={"synthetic": "a" * 64},
        limitations=["SYNTHETIC FIXTURE; NOT SCIENTIFIC OBSERVATIONS"],
    )
    (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
    return root


def test_build_and_isolation(source: Path, tmp_path: Path) -> None:
    """Building leaves all inputs byte-identical; all selections are isolated."""
    before = {p: sha256_file(p) for p in source.rglob("*") if p.is_file()}
    out = tmp_path / "new"
    manifest = build_package(source, out, Settings(pixels=480))
    assert len(manifest.files) == 11
    assert before == {p: sha256_file(p) for p in before}
    assert load_package(out) == manifest
    for selected, count in [
        ([], 0),
        (["CRATER_CATALOG"], 0),
        (["OPTICAL_IMAGE"], 2),
        (["TOPOGRAPHY"], 3),
        (["CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY"], 5),
    ]:
        content = build_content(out, "Investigate the target", selected)
        assert sum(b["type"] == "image" for b in content) == count
        if not selected:
            assert content == [{"type": "text", "text": "Investigate the target"}]
        if selected == ["OPTICAL_IMAGE"]:
            assert "terrain_summary" not in json.dumps(content)
            assert "elevation_m" not in json.dumps(content)
    # Package paths are portable; no references to the source directory are required.
    moved = tmp_path / "relocated"
    out.rename(moved)
    assert load_package(moved) == manifest
    (moved / "terrain.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        load_package(moved)


def test_iterative_real_loader_contract(source: Path, tmp_path: Path) -> None:
    """Exercise real file loading with synthetic fixtures, not real planetary data."""
    from autonomous_modality.iterative_evidence import evidence_view_loader
    from autonomous_modality.models import InputDataModality as M

    out = tmp_path / "views"
    build_package(source, out, Settings(pixels=480))
    before = {p: sha256_file(p) for p in out.rglob("*") if p.is_file()}
    loader = evidence_view_loader(out, expected_case_id=1)
    for modality in [M.CRATER_CATALOG, M.OPTICAL_IMAGE, M.TOPOGRAPHY]:
        observation = loader(modality)
        expected = build_content(out, "fixture", [modality.value])[1:]
        assert [b.model_dump(exclude_none=True) for b in observation.blocks] == expected
        assert observation.package_sha256 == sha256_file(out / "manifest.json")
    assert before == {p: sha256_file(p) for p in before}
    with pytest.raises(ValueError, match="different crater"):
        evidence_view_loader(out, expected_case_id=999)
    with pytest.raises(ValueError, match="not present"):
        loader(M.SCIENTIFIC_LITERATURE)
    (out / "terrain.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        loader(M.TOPOGRAPHY)


def test_iterative_manifest_is_pinned(source: Path, tmp_path: Path) -> None:
    from autonomous_modality.iterative_evidence import evidence_view_loader
    from autonomous_modality.models import InputDataModality as M

    out = tmp_path / "views"
    build_package(source, out, Settings(pixels=480))
    loader = evidence_view_loader(out, expected_case_id=1)
    manifest = out / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest changed"):
        loader(M.CRATER_CATALOG)


def test_existing_output_and_bad_source(source: Path, tmp_path: Path) -> None:
    """Refuse overwrite and reject corrupted source before creating output."""
    with pytest.raises(ValueError, match="new directory"):
        build_package(source, source)
    (source / "evidence/catalogue.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "new"
    with pytest.raises(ValueError, match="checksum"):
        build_package(source, out)
    assert not out.exists()


def test_numeric_profiles_and_scale(source: Path) -> None:
    """Known planar fixture verifies coordinates, scaling, missing-data propagation."""
    path = source / "evidence/dem_local.tif"
    with rasterio.open(path, "r+") as ds:
        ds.scales = (0.5,)
        ds.offsets = (10.0,)
    values, meta = read_grid(path)
    summary = terrain_summary(values, meta, "metres")
    assert summary.minimum_m == 10
    assert summary.maximum_m == 27.5
    assert summary.profiles[0].distance_km == [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]
    assert summary.profiles[0].elevation_m == [17.5, 18, 18.5, 19, 19.5, 20]
    assert summary.profiles[1].elevation_m == [26.25, 23.25, 20.25, 17.25, 14.25, 11.25]
    values[2, 0] = np.nan
    assert np.isnan(centre_profile(values, "east")[0])
    assert centre_profile(np.arange(9).reshape(3, 3), "north").tolist() == [1, 4, 7]


@pytest.mark.parametrize("selected", [["BAD"], ["TOPOGRAPHY", "TOPOGRAPHY"]])
def test_invalid_selection(selected: list[str], tmp_path: Path) -> None:
    """Reject invalid selection before touching the filesystem."""
    with pytest.raises(ValueError):
        build_content(tmp_path, "question", selected)


@pytest.mark.parametrize("pixels", [True, 479, 1601, "960"])
def test_invalid_config(pixels: object) -> None:
    """Strict configuration forbids implicit coercion and unreasonable sizes."""
    with pytest.raises(ValidationError):
        Settings(pixels=pixels)


def test_all_missing_grid(source: Path) -> None:
    """Nodata is not a numeric observation."""
    path = source / "evidence/dem_local.tif"
    with rasterio.open(path, "r+") as ds:
        ds.write(np.full((6, 6), -9999, dtype="float32"), 1)
    with pytest.raises(ValueError, match="no valid"):
        read_grid(path)


@pytest.mark.parametrize("change", ["missing", "modality", "traversal"])
def test_invalid_manifest(source: Path, tmp_path: Path, change: str) -> None:
    """Fail closed for missing representations, relabelling and unsafe paths."""
    out = tmp_path / "trial"
    build_package(source, out, Settings(pixels=480))
    path = out / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if change == "missing":
        data["files"].pop()
    elif change == "modality":
        data["files"][1]["modality"] = "CRATER_CATALOG"
    else:
        data["files"][1]["path"] = "../optical_local.png"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_package(out)


def test_catalogue_identity(source: Path, tmp_path: Path) -> None:
    """Checksums alone cannot certify a mismatched target record."""
    path = source / "package.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["case"]["id"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        build_package(source, tmp_path / "trial")


def test_cli(
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI builds a package and previews no-data without invoking any model."""
    from ams_evidence_views.cli import main

    out = tmp_path / "trial"
    monkeypatch.setattr(
        "sys.argv",
        ["run.py", "build", "--source", str(source), "--output", str(out), "--pixels", "480"],
    )
    main()
    assert json.loads(capsys.readouterr().out)["llm_called"] is False
    monkeypatch.setattr(
        "sys.argv", ["run.py", "preview", "--package", str(out), "--question", "test"]
    )
    main()
    assert json.loads(capsys.readouterr().out) == [{"type": "text", "text": "test"}]


def test_bad_grid_geometry(source: Path) -> None:
    """Reject unsupported geographic grids rather than invent kilometre axes."""
    path = source / "evidence/dem_local.tif"
    with rasterio.open(path, "r+") as ds:
        ds.crs = "EPSG:4326"
    with pytest.raises(ValueError, match="projected metre"):
        read_grid(path)


def test_failed_render_has_no_completed_manifest(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted build cannot look like a complete package."""

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic render failure")

    monkeypatch.setattr("ams_evidence_views.builder.render_map", fail)
    out = tmp_path / "trial"
    with pytest.raises(RuntimeError, match="render failure"):
        build_package(source, out)
    assert not (out / "manifest.json").exists()
    assert (source / "package.json").is_file()
