"""Offline synthetic integrity checks; fixtures are not planetary observations."""

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from PIL import Image
from pydantic import ValidationError
from rasterio.transform import from_origin

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.heldout_finalize import (
    COMPACT_IMAGES,
    CompactReceipt,
    finalize,
    verify_compact,
    verify_files,
    verify_profiles,
)
from autonomous_modality.multispectral_dataset import FourModalityManifest


def test_file_integrity(tmp_path: Path) -> None:
    path = tmp_path / "fixture.txt"
    path.write_text("synthetic", encoding="utf-8")
    pinned = {path.name: sha256_file(path)}
    verify_files(tmp_path, pinned)
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="RELEASE_FILE_CHANGED"):
        verify_files(tmp_path, pinned)


@pytest.mark.parametrize("name", ["../escape", "..\\escape", "C:/escape", "/escape"])
def test_escaping_release_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="UNSAFE_RELEASE_PATH"):
        verify_files(tmp_path, {name: "a" * 64})


@pytest.mark.parametrize("name", ["frozen", "release.json"])
def test_finalize_refuses_existing_freeze(tmp_path: Path, name: str) -> None:
    (tmp_path / name).touch()
    with pytest.raises(FileExistsError):
        finalize(tmp_path, tmp_path / "absent.json", tmp_path)


@pytest.mark.parametrize("size", [3, 4])
def test_profiles_recomputed_and_tampering_rejected(tmp_path: Path, size: int) -> None:
    data = np.arange(size * size, dtype="float32").reshape(size, size)
    affine = from_origin(-2000, 2000, 1000, 1000)
    with rasterio.open(
        tmp_path / "dem_numeric.tif",
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype="float32",
        transform=affine,
    ) as ds:
        ds.write(data, 1)
    for axis in ("east", "north"):
        values = data.mean(axis=0 if axis == "east" else 1)
        distances = (-2000 + (np.arange(size) + 0.5) * 1000) / 1000
        if axis == "north":
            distances = -distances
        order = np.argsort(distances)
        with (tmp_path / f"profile_{axis}.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([f"{axis}_from_catalogue_centre_km", "elevation_m"])
            writer.writerows(zip(distances[order], values[order], strict=True))
    verify_profiles(tmp_path)
    path = tmp_path / "profile_north.csv"
    lines = path.read_text().splitlines()
    lines[1] = lines[1].split(",")[0] + ",99999"
    path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="PROFILE_VALUE_MISMATCH"):
        verify_profiles(tmp_path)


def test_compact_inventory_and_dimensions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    compact = tmp_path / "compact"
    source.mkdir()
    compact.mkdir()
    (source / "manifest.json").write_text("{}")
    monkeypatch.setattr(
        FourModalityManifest, "model_validate_json", lambda _: SimpleNamespace(files={})
    )
    for name in COMPACT_IMAGES:
        Image.new("RGB", (448, 224)).save(compact / name)
    for name in ("terrain.txt", "multispectral.txt"):
        (compact / name).write_text("synthetic fixture")
    receipt = CompactReceipt(
        version="four-modality-compact-1.0",
        source_sha256={},
        implementation_sha256={},
        image_edge=448,
        output_sha256={p.name: sha256_file(p) for p in compact.iterdir()},
    )
    receipt_path = compact / "receipt.json"
    receipt_path.write_text(receipt.model_dump_json())
    verify_compact(source, compact)
    Image.new("RGB", (320, 160)).save(compact / COMPACT_IMAGES[0])
    receipt.output_sha256[COMPACT_IMAGES[0]] = sha256_file(compact / COMPACT_IMAGES[0])
    receipt_path.write_text(receipt.model_dump_json())
    with pytest.raises(ValueError, match="COMPACT_IMAGE_SIZE_CHANGED"):
        verify_compact(source, compact)
    del receipt.output_sha256["multispectral.txt"]
    receipt_path.write_text(receipt.model_dump_json())
    with pytest.raises(ValueError, match="COMPACT_INVENTORY_OR_SOURCE_MISMATCH"):
        verify_compact(source, compact)


def test_compact_receipt_rejects_unversioned_edge() -> None:
    with pytest.raises(ValidationError):
        CompactReceipt.model_validate_json(
            json.dumps(
                {
                    "version": "four-modality-compact-1.0",
                    "source_sha256": {},
                    "implementation_sha256": {},
                    "output_sha256": {},
                    "image_edge": 320,
                }
            )
        )
