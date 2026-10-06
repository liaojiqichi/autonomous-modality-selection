"""Explicit PDS MDR acquisition for an existing, read-only benchmark inventory."""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

import rasterio
from pydantic import Field
from rasterio.warp import transform_bounds

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import verify_package
from autonomous_modality.models import StrictModel
from autonomous_modality.pilot import RADIUS_M

BASE = "https://planetarydata.jpl.nasa.gov/img/data/messenger/MDIS/MSGRMDS_5001/"
GEO = f"+proj=longlat +R={RADIUS_M} +no_defs"


class Tile(StrictModel):
    product_id: str = Field(pattern=r"^MDIS_MDR_064PPD_H\d{2}[NS][EW]4$")
    label_path: str
    label_sha256: str
    url: str
    expected_bytes: int = Field(gt=0)
    west: float
    east: float
    south: float
    north: float


class TargetPlan(StrictModel):
    case_id: int
    name: str
    package_path: str
    package_sha256: str
    longitude_east: float
    latitude: float
    diameter_km: float
    context_bounds: list[float]
    tiles: list[str] = Field(min_length=1)


class AcquisitionPlan(StrictModel):
    version: str = "mdr-acquisition-1.0"
    created_utc: str
    source_audit: str
    source_audit_sha256: str
    targets: list[TargetPlan]
    tiles: list[Tile]


class Receipt(StrictModel):
    url: str
    retrieved_utc: str
    bytes: int
    sha256: str


def write_new(path: Path, value: StrictModel) -> None:
    """Create a persisted validated record without replacing prior records."""
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value.model_dump_json(indent=2))


def fetch(url: str, path: Path, *, expected_bytes: int | None = None) -> Path:
    """Download once, verify length, and pin a receipt; verified caches are reusable."""
    if not url.startswith(BASE):
        raise ValueError("UNEXPECTED_DOWNLOAD_HOST_OR_ARCHIVE")
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists():
        receipt = Receipt.model_validate_json(receipt_path.read_bytes())
        if receipt.url != url or sha256_file(path) != receipt.sha256:
            raise ValueError("CACHED_DOWNLOAD_CHANGED")
        if path.stat().st_size != receipt.bytes or (
            expected_bytes is not None and receipt.bytes != expected_bytes
        ):
            raise ValueError("CACHED_DOWNLOAD_SIZE_MISMATCH")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    with urlopen(
        Request(url, headers={"User-Agent": "AMS-research-data/1.0"}), timeout=90
    ) as response:
        length = response.headers.get("Content-Length")
        with partial.open("xb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
    actual = partial.stat().st_size
    if (expected_bytes is not None and actual != expected_bytes) or (
        length is not None and actual != int(length)
    ):
        raise ValueError(f"DOWNLOAD_SIZE_MISMATCH: {path.name}")
    receipt = Receipt(
        url=url,
        retrieved_utc=datetime.now(UTC).isoformat(),
        bytes=actual,
        sha256=sha256_file(partial),
    )
    partial.rename(path)
    write_new(receipt_path, receipt)
    print(f"Downloaded {path.name}: {actual:,} bytes", flush=True)
    return path


def label_number(text: str, key: str) -> float:
    """Read exactly one scalar PDS label value."""
    matches = re.findall(rf"^\s*{re.escape(key)}\s*=\s*([-+\d.eE]+)", text, re.M)
    if len(matches) != 1:
        raise ValueError(f"EXPECTED_ONE_LABEL_VALUE: {key}")
    return float(matches[0])


def parse_tile(path: Path, url: str) -> Tile:
    """Accept the documented 2017 nonpolar eight-band MDR layout only."""
    text = path.read_text(encoding="ascii")
    required = [
        'DATA_SET_ID                    = "MESS-H-MDIS-5-RDR-MDR-V1.0"',
        "BAND_STORAGE_TYPE            = BAND_SEQUENTIAL",
        "SAMPLE_TYPE                  = PC_REAL",
        'COORDINATE_SYSTEM_NAME       = "PLANETOCENTRIC"',
    ]
    if not all(item in text for item in required):
        raise ValueError("UNSUPPORTED_MDR_LABEL")
    if label_number(text, "BANDS") != 17 or label_number(text, "SAMPLE_BITS") != 32:
        raise ValueError("UNSUPPORTED_MDR_BAND_LAYOUT")
    if label_number(text, "A_AXIS_RADIUS") * 1000 != RADIUS_M:
        raise ValueError("MERCURY_RADIUS_MISMATCH")
    return Tile(
        product_id=path.stem,
        label_path=str(path.resolve()),
        label_sha256=sha256_file(path),
        url=url.replace(".LBL", ".IMG"),
        expected_bytes=int(label_number(text, "RECORD_BYTES") * label_number(text, "FILE_RECORDS")),
        west=label_number(text, "WESTERNMOST_LONGITUDE"),
        east=label_number(text, "EASTERNMOST_LONGITUDE"),
        south=label_number(text, "MINIMUM_LATITUDE"),
        north=label_number(text, "MAXIMUM_LATITUDE"),
    )


def intersects(bounds: list[float], tile: Tile) -> bool:
    """Test a target extent against an east-positive tile, accounting for longitude wrap."""
    west, south, east, north = bounds
    return (
        south < tile.north
        and north > tile.south
        and any(west + shift < tile.east and east + shift > tile.west for shift in (-360, 0, 360))
    )


def create_plan(benchmark: Path, cache: Path) -> AcquisitionPlan:
    """Use precisely the existing accepted package list; do not resample targets."""
    audit_path = benchmark / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    packages = [benchmark / item for item in audit["packages"]]
    records = []
    for path in packages:
        if not path.resolve().is_relative_to(benchmark.resolve()):
            raise ValueError("UNSAFE_PACKAGE_PATH")
        package = verify_package(path.parent)
        with rasterio.open(path.parent / "evidence/image_context.tif") as ds:
            bounds = list(transform_bounds(ds.crs, GEO, *ds.bounds, densify_pts=41))
        records.append((path, package, bounds))
    # Existing screened targets are nonpolar. Read authoritative labels before matching extents.
    tiles = []
    for chart in range(2, 15):
        directory = f"MDR/H{chart:02d}/"
        index = fetch(BASE + directory, cache / f"H{chart:02d}.html")
        names = sorted(
            set(
                re.findall(
                    r"MDIS_MDR_064PPD_H\d{2}[NS][EW]4\.LBL", index.read_text(encoding="utf-8")
                )
            )
        )
        for name in names:
            label = fetch(BASE + directory + name, cache / name)
            tile = parse_tile(label, BASE + directory + name)
            if any(intersects(bounds, tile) for _, _, bounds in records):
                tiles.append(tile)
    targets = [
        TargetPlan(
            case_id=p.case.id,
            name=p.case.name,
            package_path=str(path.resolve()),
            package_sha256=sha256_file(path),
            longitude_east=p.case.lon_e_0,
            latitude=p.case.lat_n,
            diameter_km=p.case.diameter,
            context_bounds=bounds,
            tiles=[t.product_id for t in tiles if intersects(bounds, t)],
        )
        for path, p, bounds in records
    ]
    return AcquisitionPlan(
        created_utc=datetime.now(UTC).isoformat(),
        source_audit=str(audit_path.resolve()),
        source_audit_sha256=sha256_file(audit_path),
        targets=targets,
        tiles=tiles,
    )


def download_tiles(plan: AcquisitionPlan, cache: Path) -> None:
    """Download each shared source tile once with four bounded workers."""

    def download(tile: Tile) -> None:
        fetch(tile.url, cache / f"{tile.product_id}.IMG", expected_bytes=tile.expected_bytes)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, plan.tiles))


def main() -> None:
    """Explicit network acquisition; subsequent preparation is offline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("Explicit --allow-network is required")
    args.cache.mkdir(parents=True, exist_ok=True)
    plan_path = args.cache / "plan.json"
    if plan_path.exists():
        plan = AcquisitionPlan.model_validate_json(plan_path.read_bytes())
        if Path(plan.source_audit) != (args.benchmark / "audit.json").resolve():
            raise ValueError("PLAN_BENCHMARK_MISMATCH")
        if sha256_file(Path(plan.source_audit)) != plan.source_audit_sha256:
            raise ValueError("SOURCE_AUDIT_CHANGED")
    else:
        plan = create_plan(args.benchmark, args.cache)
        write_new(plan_path, plan)
    print(
        f"Plan: {len(plan.targets)} targets, {len(plan.tiles)} tiles, "
        f"{sum(t.expected_bytes for t in plan.tiles):,} bytes",
        flush=True,
    )
    download_tiles(plan, args.cache)


if __name__ == "__main__":
    main()
