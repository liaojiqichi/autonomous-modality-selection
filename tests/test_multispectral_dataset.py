"""Offline synthetic raster and integrity tests; no scientific observations."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from autonomous_modality.multispectral_acquisition import (
    Tile,
    fetch,
    intersects,
    label_number,
    parse_tile,
)
from autonomous_modality.multispectral_dataset import crop_tiles, masks


def make_raster(path: Path, bands: int) -> Path:
    """Create a synthetic Mercury-coordinate grid for reprojection checks."""
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=40,
        height=40,
        count=bands,
        dtype="float32",
        nodata=-9999,
        crs="+proj=aeqd +lat_0=0 +lon_0=0 +R=2439400 +units=m",
        transform=from_origin(-14000, 14000, 700, 700),
    ) as ds:
        for i in range(1, bands + 1):
            ds.write(np.full((40, 40), i / 100, dtype="float32"), i)
    return path


def test_matching_footprint_and_bands(tmp_path: Path) -> None:
    reference = make_raster(tmp_path / "reference.tif", 1)
    tile = make_raster(tmp_path / "synthetic.tif", 17)
    cube, counts, coverage = crop_tiles([tile], reference)
    assert coverage.bounds == [-14000, -14000, 14000, 14000]
    assert coverage.joint_valid_fraction == 1
    assert cube.shape[0] == 8
    assert float(cube[4].mean()) == pytest.approx(0.05)
    assert float(counts.mean()) == pytest.approx(0.09)
    regions = masks(coverage, 7)
    assert len(regions) == 4 and all(mask.any() for mask in regions.values())
    assert np.max(sum(regions.values())) == 1


def test_missing_coverage_is_not_filled(tmp_path: Path) -> None:
    reference = make_raster(tmp_path / "reference.tif", 1)
    cube, counts, coverage = crop_tiles([], reference)
    assert np.isnan(cube).all() and not counts.any()
    assert coverage.joint_valid_fraction == 0


def test_reject_wrong_band_count(tmp_path: Path) -> None:
    reference = make_raster(tmp_path / "reference.tif", 1)
    with pytest.raises(ValueError, match="UNEXPECTED_PDS_RASTER"):
        crop_tiles([reference], reference)


@pytest.mark.parametrize(
    "west,east,expected", [(-50, -40, True), (310, 320, True), (10, 20, False)]
)
def test_longitude_conventions(west: float, east: float, expected: bool) -> None:
    tile = Tile(
        product_id="MDIS_MDR_064PPD_H11NW4",
        label_path="fixture",
        label_sha256="a" * 64,
        url="fixture",
        expected_bytes=1,
        west=300,
        east=330,
        south=-45,
        north=-20,
    )
    assert intersects([west, -40, east, -30], tile) == expected


@pytest.mark.parametrize("text", ["", "BANDS = x", "BANDS = 8\nBANDS = 17"])
def test_reject_ambiguous_labels(text: str) -> None:
    with pytest.raises(ValueError):
        label_number(text, "BANDS")


def test_unapproved_source_rejected_before_network(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="UNEXPECTED_DOWNLOAD"):
        fetch("https://example.com/fixture", tmp_path / "never-created")
    assert not list(tmp_path.iterdir())


def test_invalid_product_label(tmp_path: Path) -> None:
    path = tmp_path / "fixture.LBL"
    path.write_text("HTML error page", encoding="ascii")
    with pytest.raises(ValueError, match="UNSUPPORTED_MDR_LABEL"):
        parse_tile(path, "fixture")
