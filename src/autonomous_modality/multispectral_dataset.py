"""Offline four-modality package preparation with explicit technical and visual QA."""

from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path
from typing import Literal

import matplotlib
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import verify_package
from autonomous_modality.iterative import EvidenceObservation, LoadEvidence
from autonomous_modality.iterative_evidence import evidence_view_loader
from autonomous_modality.models import DataAssetProfile, InputDataModality, StrictModel
from autonomous_modality.multispectral import (
    SpectralMetadata,
    multispectral_asset,
    multispectral_loader,
    summarize_multispectral,
)
from autonomous_modality.multispectral_acquisition import (
    GEO,
    AcquisitionPlan,
    Receipt,
    TargetPlan,
    write_new,
)

matplotlib.use("Agg")
from matplotlib import pyplot as plt

WAVELENGTHS = [430, 480, 560, 630, 750, 830, 900, 1000]
NATIVE_RESOLUTION = 665.406777


class Coverage(StrictModel):
    per_band_valid_fraction: list[float]
    joint_valid_fraction: float
    width: int
    height: int
    transform: list[float]
    crs_wkt: str
    bounds: list[float]


class FourModalityManifest(StrictModel):
    version: Literal["four-modality-package-1.0"] = "four-modality-package-1.0"
    case_id: int
    name: str
    source_package_sha256: str
    source_view_manifest_sha256: str
    acquisition_plan_sha256: str
    source_tiles: dict[str, str]
    assets: list[DataAssetProfile]
    files: dict[str, str]
    context: Coverage
    local: Coverage
    technical_pass: bool
    visual_review: Literal["pending"] = "pending"
    expert_approved: Literal[False] = False
    cost_definition: str = (
        "Development ordinal units: catalogue=1, optical=2, topography=2, "
        "multispectral=2; not tokens."
    )
    registration_note: str = (
        "Same target and map footprint; no subpixel registration or accuracy claim. "
        "Visual review is recorded separately."
    )
    llm_called: Literal[False] = False


def grid(reference: Path) -> tuple[object, object, int, int, list[float]]:
    """Match the existing geographic footprint at approximately native spectral spacing."""
    with rasterio.open(reference) as ds:
        bounds = list(ds.bounds)
        width = math.ceil((ds.bounds.right - ds.bounds.left) / NATIVE_RESOLUTION)
        height = math.ceil((ds.bounds.top - ds.bounds.bottom) / NATIVE_RESOLUTION)
        return ds.crs, from_bounds(*bounds, width, height), width, height, bounds


def crop_tiles(labels: list[Path], reference: Path) -> tuple[np.ndarray, np.ndarray, Coverage]:
    """Reproject real reflectance and acquisition counts; preserve missing coverage."""
    crs, affine, width, height, bounds = grid(reference)
    cube = np.full((8, height, width), np.nan, dtype="float32")
    counts = np.zeros((height, width), dtype="float32")
    for label in labels:
        with rasterio.open(label) as ds:
            if ds.count != 17 or ds.crs is None or ds.dtypes[0] != "float32":
                raise ValueError("UNEXPECTED_PDS_RASTER")
            tile_cube = np.full_like(cube, np.nan)
            tile_count = np.zeros_like(counts)
            for band in range(8):
                reproject(
                    rasterio.band(ds, band + 1),
                    tile_cube[band],
                    dst_transform=affine,
                    dst_crs=crs,
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                )
            reproject(
                rasterio.band(ds, 9),
                tile_count,
                dst_transform=affine,
                dst_crs=crs,
                dst_nodata=0,
                resampling=Resampling.nearest,
            )
            valid = np.isfinite(tile_cube).all(axis=0) & (tile_cube > -1e30).all(axis=0)
            valid &= tile_count > 0
            # Stable first-valid mosaic order; source tile overlaps are not averaged again.
            take = valid & ~np.isfinite(cube).all(axis=0)
            cube[:, take] = tile_cube[:, take]
            counts[take] = tile_count[take]
    coverage = Coverage(
        per_band_valid_fraction=[float(np.isfinite(b).mean()) for b in cube],
        joint_valid_fraction=float(np.isfinite(cube).all(axis=0).mean()),
        width=width,
        height=height,
        transform=list(affine),
        crs_wkt=crs.to_wkt(),
        bounds=bounds,
    )
    return cube, counts, coverage


def masks(coverage: Coverage, diameter_km: float) -> dict[str, np.ndarray]:
    """Fixed geometric sampling zones, not interpreted geological boundaries."""
    left, bottom, right, top = coverage.bounds
    x = left + (np.arange(coverage.width) + 0.5) * (right - left) / coverage.width
    y = top - (np.arange(coverage.height) + 0.5) * (top - bottom) / coverage.height
    radius = np.hypot(x[None, :], y[:, None]) / (diameter_km * 1000)
    return {
        "roi_inner_disk_r_lt_025D": radius < 0.25,
        "roi_middle_annulus_r_025_to_05D": (radius >= 0.25) & (radius < 0.5),
        "roi_outer_annulus_r_05_to_10D": (radius >= 0.5) & (radius < 1),
        "roi_background_annulus_r_10_to_20D": (radius >= 1) & (radius < 2),
    }


def stretch(array: np.ndarray) -> np.ndarray:
    """Display-only percentile scaling; quantitative arrays are retained unchanged."""
    low, high = np.nanpercentile(array, [2, 98])
    return np.clip((array - low) / max(float(high - low), 1e-12), 0, 1)


def review_figure(
    root: Path,
    base: Path,
    local: np.ndarray,
    context: np.ndarray,
    local_coverage: Coverage,
    context_coverage: Coverage,
    name: str,
) -> None:
    """Create spatially matched panels for direct visual review."""
    with rasterio.open(base / "evidence/image_local.tif") as ds:
        optical = ds.read(1, masked=True).filled(np.nan)
        optical_bounds = ds.bounds
    with rasterio.open(base / "evidence/dem_local.tif") as ds:
        dem = ds.read(1, masked=True).filled(np.nan)
        dem_bounds = ds.bounds
    with rasterio.open(base / "evidence/image_context.tif") as ds:
        optical_context = ds.read(1, masked=True).filled(np.nan)
    fig, axes = plt.subplots(2, 3, figsize=(15, 10), constrained_layout=True)
    panels = [
        (optical, optical_bounds, "Existing optical local"),
        (local[4], local_coverage.bounds, "MDR 750 nm local"),
        (dem, dem_bounds, "Existing DEM local"),
        (optical_context, context_coverage.bounds, "Existing optical context"),
        (context[4], context_coverage.bounds, "MDR 750 nm context"),
        (
            np.stack([stretch(local[i]) for i in [7, 4, 0]], axis=-1),
            local_coverage.bounds,
            "MDR 1000/750/430 display composite",
        ),
    ]
    for ax, (array, bounds, title) in zip(axes.flat, panels, strict=True):
        left, bottom, right, top = np.array(bounds) / 1000
        ax.imshow(
            stretch(array) if array.ndim == 2 else array,
            extent=[left, right, bottom, top],
            cmap="gray",
            origin="upper",
        )
        ax.plot(0, 0, "+", color="red", markersize=9)
        ax.set(title=title, xlabel="Local east (km)", ylabel="Local north (km)")
    fig.suptitle(f"{name}: same map footprints; red cross is the catalogue coordinate")
    fig.savefig(root / "correspondence_review.png", dpi=120)
    plt.close(fig)


def prepare_target(
    target: TargetPlan, plan: AcquisitionPlan, plan_path: Path, views: Path, output: Path
) -> FourModalityManifest:
    """Build a self-contained four-modality development input package."""
    from ams_evidence_views.adapter import load_package

    base = Path(target.package_path).parent
    if sha256_file(Path(target.package_path)) != target.package_sha256:
        raise ValueError("SOURCE_PACKAGE_CHANGED")
    original = verify_package(base)
    if original.case.id != target.case_id:
        raise ValueError("CASE_ID_MISMATCH")
    view_root = views / f"crater-{target.case_id}"
    view_manifest = load_package(view_root)
    if (
        view_manifest.case_id != target.case_id
        or view_manifest.source_package_sha256 != target.package_sha256
    ):
        raise ValueError("CORE_VIEW_PACKAGE_MISMATCH")
    labels = []
    hashes = {}
    for tile in plan.tiles:
        if tile.product_id not in target.tiles:
            continue
        label = Path(tile.label_path)
        if sha256_file(label) != tile.label_sha256:
            raise ValueError("PDS_LABEL_CHANGED")
        image = label.with_suffix(".IMG")
        receipt = Receipt.model_validate_json(image.with_suffix(".IMG.receipt.json").read_bytes())
        if (
            image.stat().st_size != tile.expected_bytes
            or receipt.url != tile.url
            or sha256_file(image) != receipt.sha256
        ):
            raise ValueError("SOURCE_TILE_CHANGED")
        hashes[image.name] = receipt.sha256
        hashes[label.name] = tile.label_sha256
        labels.append(label)
    context, counts, coverage = crop_tiles(labels, base / "evidence/image_context.tif")
    local, _, local_coverage = crop_tiles(labels, base / "evidence/image_local.tif")
    # Confirm the existing local projection is centered on the same catalogue target.
    xs, ys = transform(GEO, coverage.crs_wkt, [target.longitude_east], [target.latitude])
    if math.hypot(xs[0], ys[0]) > 1:
        raise ValueError("TARGET_GRID_CENTER_MISMATCH")
    root = output / f"crater-{target.case_id}"
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(view_root, root / "core_views", ignore=shutil.ignore_patterns("__pycache__"))
    source = root / "multispectral.npz"
    np.savez_compressed(
        source,
        reflectance=context,
        source_image_count=counts,
        **masks(coverage, target.diameter_km),
    )
    metadata = SpectralMetadata(
        case_id=str(target.case_id),
        product_id="+".join(target.tiles),
        source_uri="https://planetarydata.jpl.nasa.gov/img/data/messenger/MDIS/MSGRMDS_5001/",
        instrument="MESSENGER_MDIS_WAC",
        quantity="radiance_factor_I_over_F",
        processing="calibrated_photometrically_corrected",
        calibration_reference="MDIS CDR/RDR SIS 1.2.23, section 2.5.2.3, MDR version 4; 2017-03-21",
        spatial_reference=coverage.crs_wkt,
        pixel_resolution_m=(coverage.bounds[2] - coverage.bounds[0]) / coverage.width,
        coverage_description=(
            "Exact existing optical context footprint; four fixed geometric radial zones."
        ),
        registration_limitations=(
            "Map reprojection only; no subpixel correction. "
            "Mask names are geometric, not geological."
        ),
        provenance_kind="observed",
        bands=[{"band_id": f"WAC_{w}", "wavelength_nm": w} for w in WAVELENGTHS],
    )
    package = summarize_multispectral(source, metadata)
    write_new(root / "summary.json", package)
    for filename, cube, cov in [
        ("multispectral_local.tif", local, local_coverage),
        ("multispectral_context.tif", context, coverage),
    ]:
        with rasterio.open(
            root / filename,
            "w",
            driver="GTiff",
            width=cov.width,
            height=cov.height,
            count=8,
            dtype="float32",
            crs=cov.crs_wkt,
            transform=rasterio.Affine(*cov.transform[:6]),
            nodata=np.nan,
            compress="deflate",
        ) as ds:
            ds.write(cube)
            for band, wavelength in enumerate(WAVELENGTHS, 1):
                ds.set_band_description(band, f"{wavelength} nm, photometrically normalized I/F")
    review_figure(root, base, local, context, local_coverage, coverage, target.name)
    asset = multispectral_asset(package, estimated_cost=2)
    assets = [a.model_copy(deep=True) for a in original.assets] + [asset]
    for item in assets:
        item.source_uri = (
            "summary.json"
            if item.modality == InputDataModality.MULTISPECTRAL_IMAGE
            else "core_views/manifest.json"
        )
    manifest = FourModalityManifest(
        case_id=target.case_id,
        name=target.name,
        source_package_sha256=target.package_sha256,
        source_view_manifest_sha256=sha256_file(view_root / "manifest.json"),
        acquisition_plan_sha256=sha256_file(plan_path),
        source_tiles=hashes,
        assets=assets,
        files={
            str(p.relative_to(root)).replace("\\", "/"): sha256_file(p)
            for p in sorted(root.rglob("*"))
            if p.is_file()
        },
        context=coverage,
        local=local_coverage,
        technical_pass=min(coverage.joint_valid_fraction, local_coverage.joint_valid_fraction)
        >= 0.95,
    )
    write_new(root / "manifest.json", manifest)
    verify_package(base)
    print(
        f"Prepared {target.name}: local={local_coverage.joint_valid_fraction:.4%}, "
        f"context={coverage.joint_valid_fraction:.4%}",
        flush=True,
    )
    return manifest


def four_modality_loader(root: Path) -> LoadEvidence:
    """Route verified core and spectral observations without exposing QA to the model."""
    path = root / "manifest.json"
    manifest_hash = sha256_file(path)
    manifest = FourModalityManifest.model_validate_json(path.read_bytes())
    if not manifest.technical_pass:
        raise ValueError("FOUR_MODALITY_TECHNICAL_QA_FAILED")
    for name, digest in manifest.files.items():
        file = (root / name).resolve()
        if not file.is_relative_to(root.resolve()) or sha256_file(file) != digest:
            raise ValueError("FOUR_MODALITY_FILE_CHANGED")
    core = evidence_view_loader(root / "core_views", expected_case_id=manifest.case_id)
    spectral = multispectral_loader(
        root / "summary.json",
        expected_case_id=str(manifest.case_id),
        source_path=root / "multispectral.npz",
    )

    def load(modality: InputDataModality) -> EvidenceObservation:
        if sha256_file(path) != manifest_hash:
            raise ValueError("FOUR_MODALITY_MANIFEST_CHANGED")
        return (
            spectral(modality)
            if modality == InputDataModality.MULTISPECTRAL_IMAGE
            else core(modality)
        )

    return load


class BatchEntry(StrictModel):
    case_id: int
    name: str
    status: Literal["prepared", "coverage_failed", "error"]
    error: str | None = None


class BatchReport(StrictModel):
    version: str = "four-modality-batch-1.0"
    plan_sha256: str
    implementation_sha256: str
    cases: list[BatchEntry]
    llm_called: Literal[False] = False


def main() -> None:
    """Prepare all planned targets, retaining explicit failure records."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = AcquisitionPlan.model_validate_json(args.plan.read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.plan, args.output / "acquisition_plan.json")
    entries = []
    for target in plan.targets:
        try:
            result = prepare_target(target, plan, args.plan, args.views, args.output)
            entries.append(
                BatchEntry(
                    case_id=target.case_id,
                    name=target.name,
                    status="prepared" if result.technical_pass else "coverage_failed",
                )
            )
        except Exception as exc:
            print(f"Failed {target.name}: {type(exc).__name__}: {exc}", flush=True)
            entries.append(
                BatchEntry(
                    case_id=target.case_id,
                    name=target.name,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    write_new(
        args.output / "batch_report.json",
        BatchReport(
            plan_sha256=sha256_file(args.plan),
            implementation_sha256=sha256_file(Path(__file__)),
            cases=entries,
        ),
    )
    if any(entry.status != "prepared" for entry in entries):
        raise SystemExit("Some targets failed; inspect batch_report.json")


if __name__ == "__main__":
    main()
