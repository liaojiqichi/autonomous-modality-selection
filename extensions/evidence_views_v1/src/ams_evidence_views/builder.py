"""Read existing packages; write only into a newly created trial directory."""

import csv
import importlib.metadata
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import local_file, verify_package
from autonomous_modality.pilot import CatalogueRow

from .models import Manifest, Modality, Product, Profile, Settings, TerrainSummary


def read_grid(path: Path) -> tuple[np.ndarray, dict]:
    """Read one projected north-up square grid; apply scale after masking."""
    with rasterio.open(path) as ds:
        t = ds.transform
        if (
            ds.count != 1
            or ds.crs is None
            or not ds.crs.is_projected
            or ds.crs.linear_units != "metre"
            or t.a <= 0
            or t.e >= 0
            or t.b != 0
            or t.d != 0
            or not np.isclose(t.a, -t.e)
        ):
            raise ValueError("requires single-band, projected metre, north-up square grid")
        values = ds.read(1, masked=True).astype(float).filled(np.nan)
        values = values * ds.scales[0] + ds.offsets[0]
        values[~np.isfinite(values)] = np.nan
        if not np.isfinite(values).any():
            raise ValueError("grid has no valid numeric pixels")
        meta = {
            "crs_wkt": ds.crs.to_wkt(),
            "transform": list(t)[:6],
            "source_scale": float(ds.scales[0]),
            "source_offset": float(ds.offsets[0]),
            "bounds": list(ds.bounds),
        }
    return values, meta


def centre_profile(values: np.ndarray, axis: str) -> np.ndarray:
    """For even dimensions require both middle rows/columns to be valid."""
    if axis not in {"east", "north"} or values.ndim != 2:
        raise ValueError("invalid profile axis or grid")
    lines = values if axis == "east" else values.T
    n = len(lines)
    return lines[n // 2].copy() if n % 2 else (lines[n // 2 - 1] + lines[n // 2]) / 2


def terrain_summary(values: np.ndarray, meta: dict, units: str) -> TerrainSummary:
    """Calculate reproducible whole-crop statistics and orthogonal cross-sections."""
    height, width = values.shape
    a, _, c, _, e, f = meta["transform"]
    # Coordinates relative to the source projected origin (catalogue centre), not array centre.
    x = (c + (np.arange(width) + 0.5) * a) / 1000
    y = (f + (np.arange(height) + 0.5) * e) / 1000
    profiles = []
    for axis, distances in [("east", x), ("north", y)]:
        elevations = centre_profile(values, axis)
        order = np.argsort(distances)
        profiles.append(
            Profile(
                axis=axis,
                distance_km=[float(distances[i]) for i in order],
                elevation_m=[
                    float(elevations[i]) if np.isfinite(elevations[i]) else None for i in order
                ],
            )
        )
    finite = values[np.isfinite(values)]
    return TerrainSummary(
        shape=[height, width],
        source_units=units,
        **{k: v for k, v in meta.items() if k != "bounds"},
        valid_fraction=float(len(finite) / values.size),
        minimum_m=float(finite.min()),
        maximum_m=float(finite.max()),
        mean_m=float(finite.mean()),
        std_m=float(finite.std()),
        profiles=profiles,
    )


def render_map(
    path: Path, values: np.ndarray, meta: dict, title: str, pixels: int, terrain: bool
) -> None:
    """Fixed-size labelled map; optical display uses fixed 0--255 DN limits."""
    left, bottom, right, top = np.array(meta["bounds"]) / 1000
    fig, ax = plt.subplots(figsize=(pixels / 120, pixels / 120), dpi=120)
    opts = {} if terrain else {"vmin": 0, "vmax": 255}
    im = ax.imshow(
        values,
        extent=(left, right, bottom, top),
        origin="upper",
        cmap="viridis" if terrain else "gray",
        interpolation="nearest",
        **opts,
    )
    ax.set(
        title=title,
        xlabel="East from catalogue centre (km)",
        ylabel="North from catalogue centre (km)",
    )
    if terrain:
        ax.axhline((bottom + top) / 2, color="white", linewidth=0.7, linestyle="--")
        ax.axvline((left + right) / 2, color="white", linewidth=0.7, linestyle="--")
        fig.colorbar(im, ax=ax, label="Elevation (m); source reference")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def render_profile(path: Path, profile: Profile, pixels: int) -> None:
    """Plot a numerical profile without filling missing samples."""
    fig, ax = plt.subplots(figsize=(pixels / 120, pixels / 240), dpi=120)
    ax.plot(
        profile.distance_km, [np.nan if v is None else v for v in profile.elevation_m], linewidth=1
    )
    ax.set(
        title=f"Central {profile.axis} profile (not crater depth)",
        xlabel=f"{profile.axis.capitalize()} from catalogue centre (km)",
        ylabel="Elevation (m)",
    )
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def build_package(source: Path, output: Path, settings: Settings | None = None) -> Manifest:
    """Build new representations; never overwrite a directory or original evidence."""
    settings = settings or Settings()
    source, output = source.resolve(), output.resolve()
    if output.exists() or source.is_relative_to(output):
        raise ValueError("output must be a new directory and cannot contain the source")
    package = verify_package(source)
    package_digest = sha256_file(source / "package.json")
    files = {item.path: item for item in package.files}
    required = {
        "evidence/catalogue.json": "CRATER_CATALOG",
        "evidence/image_local.tif": "OPTICAL_IMAGE",
        "evidence/image_context.tif": "OPTICAL_IMAGE",
        "evidence/dem_local.tif": "TOPOGRAPHY",
    }
    for name, modality in required.items():
        if name not in files or files[name].modality.value != modality:
            raise ValueError(f"missing or wrong-modality source: {name}")
    catalogue = CatalogueRow.model_validate_json(
        (source / "evidence/catalogue.json").read_text(encoding="utf-8")
    )
    if catalogue != package.case:
        raise ValueError("catalogue identity differs from source package")
    grids = {name: read_grid(local_file(source, name)) for name in required if name.endswith("tif")}
    for name, (_, meta) in grids.items():
        # Existing packages use a catalogue-centred projection; reject mismatches.
        crs = rasterio.crs.CRS.from_wkt(meta["crs_wkt"]).to_dict()
        if (
            crs.get("proj") != "aeqd"
            or not np.isclose(crs.get("lat_0", 999), package.case.lat_n)
            or not np.isclose(crs.get("lon_0", 999), package.case.lon_e_0)
        ):
            raise ValueError(f"grid is not centred on the catalogue target: {name}")
    dem_name = "evidence/dem_local.tif"
    summary = terrain_summary(*grids[dem_name], files[dem_name].units)
    if "metre" not in summary.source_units.lower() and "meter" not in summary.source_units.lower():
        raise ValueError("DEM requires documented metre units")
    output.mkdir(parents=True, exist_ok=False)
    products = []

    def record(name: str, modality: Modality, kind: str, parent: str) -> None:
        path = output / name
        products.append(
            Product(
                path=name,
                modality=modality,
                kind=kind,
                sha256=sha256_file(path),
                bytes=path.stat().st_size,
                parents={parent: files[parent].sha256},
            )
        )

    shutil.copyfile(source / "evidence/catalogue.json", output / "catalogue.json")
    record("catalogue.json", "CRATER_CATALOG", "text", "evidence/catalogue.json")
    for label in ["local", "context"]:
        parent = f"evidence/image_{label}.tif"
        name = f"optical_{label}.png"
        render_map(
            output / name,
            *grids[parent],
            f"{package.case.name}: optical {label}",
            settings.pixels,
            False,
        )
        record(name, "OPTICAL_IMAGE", "image", parent)
    shutil.copyfile(source / dem_name, output / "dem_numeric.tif")
    record("dem_numeric.tif", "TOPOGRAPHY", "numeric", dem_name)
    render_map(
        output / "elevation.png",
        *grids[dem_name],
        f"{package.case.name}: elevation",
        settings.pixels,
        True,
    )
    record("elevation.png", "TOPOGRAPHY", "image", dem_name)
    (output / "terrain_summary.json").write_text(
        summary.model_dump_json(indent=2), encoding="utf-8"
    )
    record("terrain_summary.json", "TOPOGRAPHY", "numeric", dem_name)
    for profile in summary.profiles:
        name = f"profile_{profile.axis}"
        with (output / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([f"{profile.axis}_from_catalogue_centre_km", "elevation_m"])
            writer.writerows(zip(profile.distance_km, profile.elevation_m, strict=True))
        record(f"{name}.csv", "TOPOGRAPHY", "numeric", dem_name)
        render_profile(output / f"{name}.png", profile, settings.pixels)
        record(f"{name}.png", "TOPOGRAPHY", "image", dem_name)
    sampled = summary.model_dump()
    for profile in sampled["profiles"]:
        indices = np.unique(
            np.linspace(
                0, len(profile["distance_km"]) - 1, settings.profile_text_samples, dtype=int
            )
        )
        for key in ["distance_km", "elevation_m"]:
            profile[key] = [profile[key][i] for i in indices]
    text = (
        "Whole-crop statistics, not crater depth or rim height. Profiles are fixed central "
        "cross-sections; even dimensions average two lines only where both are valid. "
        "Below are uniformly index-sampled numeric values, not extrema-preserving samples. "
        "Null means missing. Optical and DEM share MDIS ancestry.\n" + json.dumps(sampled)
    )
    (output / "terrain.txt").write_text(text, encoding="utf-8")
    record("terrain.txt", "TOPOGRAPHY", "text", dem_name)
    # Recheck sources after processing; do not certify a package built from changing files.
    verify_package(source)
    if sha256_file(source / "package.json") != package_digest:
        raise ValueError("source manifest changed during preparation")
    manifest = Manifest(
        settings=settings,
        case_id=package.case.id,
        case_name=package.case.name,
        source_package_sha256=package_digest,
        source_files={k: v.sha256 for k, v in files.items()},
        implementation_sha256={p.name: sha256_file(p) for p in Path(__file__).parent.glob("*.py")},
        software_versions={
            n: importlib.metadata.version(n)
            for n in ["numpy", "rasterio", "matplotlib", "pydantic"]
        },
        files=products,
    )
    (output / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
