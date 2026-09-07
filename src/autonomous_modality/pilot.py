"""Offline real-product preparation and deterministic selection pilot (no LLM calls)."""
# Chinese report text deliberately uses Chinese punctuation.
# ruff: noqa: RUF001

from __future__ import annotations

import argparse
import csv
import html
import math
import platform
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from string import Template
from typing import Annotated, Literal, Self

import matplotlib
import numpy as np
import rasterio
from pydantic import Field, model_validator
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from autonomous_modality.acquisition import DownloadRecord, load_sources, sha256_file
from autonomous_modality.models import (
    AssetAvailability,
    BaselineSelectionResult,
    CraterQuestion,
    CraterQuestionType,
    CraterReference,
    DataAssetProfile,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
    NonEmptyString,
    SpatialCoverage,
    StrictModel,
)
from autonomous_modality.selection import select_baseline

matplotlib.use("Agg")
from matplotlib import pyplot as plt

PILOT_VERSION = "mercury-real-pilot-1.1"
RADIUS_M = 2439400.0
CATALOGUE_LIMIT = (
    "Herrick 2011 flyby-era catalogue: historical coordinates and loose morphology labels; "
    "registration with orbital mosaics requires manual review. Not the 2018 catalogue."
)


class CatalogueRow(StrictModel):
    """Validated numeric coordinates with unmodified historical morphology codes."""

    id: Annotated[int, Field(gt=0)]
    lat_n: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    lon_e_0: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    int_shp: str
    rim_shp: str
    cent_struc: str
    rayed: str
    name: str
    diameter: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class PilotConfig(StrictModel):
    """Pinned, deliberately limited sampling and preparation policy."""

    version: Literal["mercury-real-pilot-1.0", "mercury-real-pilot-1.1"] = PILOT_VERSION
    sample_count: Annotated[int, Field(ge=1, le=20)] = 12
    minimum_valid_fraction: Annotated[float, Field(ge=0, le=1)] = 0.95
    minimum_diameter_km: Literal[50] = 50
    maximum_diameter_km: Literal[150] = 150
    latitude_limit_deg: Literal[45] = 45
    local_width_diameters: Literal[2] = 2
    context_width_diameters: Literal[5] = 5
    cost_definition: str = (
        "Ordinal experimental input units: catalogue=1, image=2, topography=2; "
        "not measured latency or tokens."
    )


class RasterProduct(StrictModel):
    """Preparation record for a numeric derived raster and its display."""

    source_id: str
    source_sha256: str
    source_crs_wkt: str
    source_scale: float
    source_offset: float
    source_nodata: float | None
    source_window: list[int]
    derived_crs_wkt: str
    resolution_m: float
    width_pixels: int
    valid_fraction: Annotated[float, Field(ge=0, le=1)]
    units: str
    resampling: str = "bilinear"
    data_path: str
    data_sha256: str
    preview_path: str
    minimum: float | None
    maximum: float | None
    percentile_5: float | None
    percentile_95: float | None


class PilotCase(StrictModel):
    """A real catalogue target and its actual prepared input products."""

    catalogue: CatalogueRow
    products: list[RasterProduct]
    assets: list[DataAssetProfile]
    accepted: bool
    limitations: list[str]
    profile_path: str
    overview_path: str


class SelectionTrial(StrictModel):
    """A persisted input and output; no generated solution or expert score implied."""

    case_id: int
    condition: str
    request: InputSelectionRequest
    result: BaselineSelectionResult | None = None
    error: NonEmptyString | None = None

    @model_validator(mode="after")
    def ensure_one_outcome(self) -> Self:
        """Persist exactly one successful result or explicit failure."""
        if (self.result is None) == (self.error is None):
            raise ValueError("trial requires exactly one result or error")
        return self


class PilotRun(StrictModel):
    """Run-level provenance and explicit limits of this engineering experiment."""

    schema_version: Literal["pilot-run-1.0", "pilot-run-1.1"] = "pilot-run-1.1"
    run_id: NonEmptyString
    created_utc: datetime
    config: PilotConfig
    code_sha256: dict[str, str]
    environment: dict[str, str]
    sources: list[DownloadRecord]
    catalogue_rows: int
    eligible_rows: int
    sampling: str
    cases: list[PilotCase]
    trials: list[SelectionTrial]
    limitations: list[str]
    llm_called: Literal[False] = False
    observed_solution_richness: None = None


def load_catalogue(path: Path) -> list[CatalogueRow]:
    """Read all source rows strictly, rejecting unknown columns, invalid values and IDs."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != set(CatalogueRow.model_fields) or len(
            reader.fieldnames or []
        ) != len(CatalogueRow.model_fields):
            raise ValueError("unexpected catalogue columns")
        rows = [CatalogueRow.model_validate(row) for row in reader]
    if not rows or len({row.id for row in rows}) != len(rows):
        raise ValueError("catalogue is empty or contains duplicate IDs")
    return rows


def choose_targets(rows: list[CatalogueRow], config: PilotConfig) -> tuple[list[CatalogueRow], int]:
    """Select evenly spaced diameter ranks of named, mid-latitude, seam-free targets."""
    eligible = sorted(
        (
            row
            for row in rows
            if row.name
            and config.minimum_diameter_km <= row.diameter <= config.maximum_diameter_km
            and abs(row.lat_n) < config.latitude_limit_deg
            and 15 < abs(row.lon_e_0) < 150
        ),
        key=lambda row: (row.diameter, row.id),
    )
    if len(eligible) < config.sample_count:
        raise ValueError("too few eligible craters for the configured pilot")
    indices = np.linspace(0, len(eligible) - 1, config.sample_count, dtype=int)
    return [eligible[int(index)] for index in indices], len(eligible)


def scaled_dem(values: np.ma.MaskedArray, scale: float, offset: float) -> np.ndarray:
    """Apply TIFF scale/offset only after masking source nodata."""
    if not math.isfinite(scale) or scale <= 0 or not math.isfinite(offset):
        raise ValueError("invalid DEM scale or offset")
    return values.astype("float32").filled(np.nan) * scale + offset


def crop_product(
    source_path: Path,
    source: DownloadRecord,
    target: CatalogueRow,
    width_diameters: int,
    destination: Path,
    topography: bool,
) -> tuple[RasterProduct, np.ndarray]:
    """Reproject a bounded source window into a target-centred Mercury AEQD grid."""
    if width_diameters not in (2, 5):
        raise ValueError("pilot crop width must be two or five diameters")
    if "raw" in [part.lower() for part in destination.resolve().parts]:
        raise ValueError("derived output must be outside data/raw")
    if destination.exists() or destination.with_suffix(".png").exists():
        raise FileExistsError("derived product already exists")
    local_crs = CRS.from_string(
        f"+proj=aeqd +lat_0={target.lat_n} +lon_0={target.lon_e_0} +R={RADIUS_M} +units=m +no_defs"
    )
    with rasterio.open(source_path) as dataset:
        if dataset.count != 1 or dataset.crs is None:
            raise ValueError("expected single-band georeferenced source")
        if "Mercury" not in dataset.crs.to_wkt():
            raise ValueError("source CRS must explicitly identify Mercury")
        if not dataset.crs.is_projected or dataset.crs.linear_units_factor[1] != 1:
            raise ValueError("source grid must be projected in metres")
        if (
            dataset.transform.b != 0
            or dataset.transform.d != 0
            or dataset.transform.a <= 0
            or dataset.transform.e >= 0
            or not math.isclose(dataset.res[0], dataset.res[1], rel_tol=1e-9)
        ):
            raise ValueError("source grid must be north-up with square pixels")
        resolution = float(dataset.res[0])
        size = math.ceil(target.diameter * 1000 * width_diameters / resolution)
        if size > 6000:
            raise ValueError("crop exceeds pilot memory limit")
        half = size * resolution / 2
        bounds = transform_bounds(local_crs, dataset.crs, -half, -half, half, half, densify_pts=21)
        window_float = from_bounds(*bounds, transform=dataset.transform)
        left = math.floor(window_float.col_off) - 2
        top = math.floor(window_float.row_off) - 2
        right = math.ceil(window_float.col_off + window_float.width) + 2
        bottom = math.ceil(window_float.row_off + window_float.height) + 2
        if left < 0 or top < 0 or right > dataset.width or bottom > dataset.height:
            raise ValueError("crop crosses source boundary or longitude seam")
        window = Window(left, top, right - left, bottom - top)
        raw = dataset.read(1, window=window, masked=True)
        # LOI is already an 8-bit display stretch. Retain its DN, not a reflectance claim.
        values = (
            scaled_dem(raw, dataset.scales[0], dataset.offsets[0])
            if topography
            else raw.astype("float32").filled(np.nan)
        )
        array = np.full((size, size), np.nan, dtype="float32")
        transform = from_origin(-half, half, resolution, resolution)
        reproject(
            values,
            array,
            src_transform=dataset.window_transform(window),
            src_crs=dataset.crs,
            src_nodata=np.nan,
            dst_transform=transform,
            dst_crs=local_crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        with rasterio.open(
            destination,
            "w",
            driver="GTiff",
            width=size,
            height=size,
            count=1,
            dtype="float32",
            nodata=np.nan,
            crs=local_crs,
            transform=transform,
            compress="deflate",
        ) as output:
            output.write(array, 1)
            output.update_tags(
                source_sha256=source.sha256,
                pilot_version=PILOT_VERSION,
                units="metres" if topography else "stretched image DN",
            )
        finite = array[np.isfinite(array)]
        product = RasterProduct(
            source_id=source.source.source_id,
            source_sha256=source.sha256,
            source_crs_wkt=dataset.crs.to_wkt(),
            source_scale=dataset.scales[0],
            source_offset=dataset.offsets[0],
            source_nodata=dataset.nodata,
            source_window=[left, top, right - left, bottom - top],
            derived_crs_wkt=local_crs.to_wkt(),
            resolution_m=resolution,
            width_pixels=size,
            valid_fraction=float(finite.size / array.size),
            units="metres relative to 2439.4 km radius"
            if topography
            else "8-bit stretched image DN, resampled",
            data_path=str(destination),
            data_sha256=sha256_file(destination),
            preview_path=str(destination.with_suffix(".png")),
            minimum=float(finite.min()) if finite.size else None,
            maximum=float(finite.max()) if finite.size else None,
            percentile_5=float(np.percentile(finite, 5)) if finite.size else None,
            percentile_95=float(np.percentile(finite, 95)) if finite.size else None,
        )
    fig, axis = plt.subplots(figsize=(6, 6), layout="constrained")
    extent = [-half / 1000, half / 1000, -half / 1000, half / 1000]
    display = axis.imshow(
        array,
        extent=extent,
        cmap="terrain" if topography else "gray",
        vmin=None if topography else 1,
        vmax=None if topography else 255,
    )
    axis.set(
        title=f"{target.name} | {width_diameters}D | {'DEM' if topography else 'MDIS LOI'}",
        xlabel="East from catalogue centre (km)",
        ylabel="North (km)",
    )
    axis.plot(0, 0, "+", color="red", markersize=7)
    if topography:
        fig.colorbar(display, ax=axis, shrink=0.7, label="Elevation (m)")
    fig.savefig(product.preview_path, dpi=130)
    plt.close(fig)
    return product, array


def make_case(
    row: CatalogueRow, records: dict[str, DownloadRecord], root: Path, config: PilotConfig
) -> PilotCase:
    """Create real numerical crops, readable previews and selector asset descriptions."""
    directory = root / f"crater-{row.id}"
    directory.mkdir()
    with (directory / "catalogue.json").open("x", encoding="utf-8") as stream:
        stream.write(row.model_dump_json(indent=2))
    products: list[RasterProduct] = []
    arrays: list[np.ndarray] = []
    for source_id, width, filename in (
        ("mdis-loi-v1", config.local_width_diameters, "image_local.tif"),
        ("mdis-loi-v1", config.context_width_diameters, "image_context.tif"),
        ("usgs-dem-v2", config.local_width_diameters, "dem_local.tif"),
    ):
        record = records[source_id]
        product, array = crop_product(
            Path(record.path), record, row, width, directory / filename, source_id == "usgs-dem-v2"
        )
        products.append(product)
        arrays.append(array)
    dem = arrays[2]
    n = dem.shape[0]
    # Odd/even grids handled explicitly: average the two central rows for an even grid.
    mid = n // 2
    profile = dem[mid, :] if n % 2 else (dem[mid - 1, :] + dem[mid, :]) / 2
    distances = (np.arange(n) + 0.5 - n / 2) * products[2].resolution_m / 1000
    profile_path = directory / "east_west_profile.csv"
    with profile_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["east_from_catalogue_centre_km", "elevation_m"])
        writer.writerows(
            (float(x), float(y) if np.isfinite(y) else "")
            for x, y in zip(distances, profile, strict=True)
        )
    overview = directory / "overview.png"
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), layout="constrained")
    for axis, array, product, label in zip(
        axes[:2],
        arrays[:2],
        products[:2],
        ("Local: 2 diameters", "Context: 5 diameters"),
        strict=True,
    ):
        half = product.width_pixels * product.resolution_m / 2000
        axis.imshow(array, cmap="gray", vmin=1, vmax=255, extent=[-half, half, -half, half])
        axis.plot(0, 0, "r+", markersize=6)
        axis.set(title=label, xlabel="East (km)", ylabel="North (km)")
    axes[2].plot(distances, profile, linewidth=1)
    axes[2].set(
        title="Centre E-W profile (not crater depth)", xlabel="East (km)", ylabel="Elevation (m)"
    )
    axes[2].grid(alpha=0.25)
    fig.suptitle(f"{row.name} | historical catalogue ID {row.id} | D={row.diameter:g} km")
    fig.savefig(overview, dpi=140)
    plt.close(fig)
    limitations = [
        CATALOGUE_LIMIT,
        "DEM and image share MDIS ancestry; they are not independent observations.",
        "Valid-pixel coverage does not establish accuracy or crater-centre registration.",
        "DEM summaries cover the whole crop, not measured crater depth or rim height.",
    ]
    assets = [
        DataAssetProfile(
            asset_id=f"herrick-2011-{row.id}",
            modality=InputDataModality.CRATER_CATALOG,
            title=f"Herrick 2011 catalogue record: {row.name}",
            source_uri=str(directory / "catalogue.json"),
            data_format="JSON",
            model_representations=["structured numeric record with historical morphology codes"],
            analytical_capabilities=["diameter comparison", "catalogue morphology comparison"],
            explanatory_capabilities=["historical morphological classification perspective"],
            limitations=[CATALOGUE_LIMIT],
            estimated_cost=1,
        )
    ]
    for modality, selected_products, capabilities in (
        (
            InputDataModality.OPTICAL_IMAGE,
            products[:2],
            ["visible morphology", "regional context comparison"],
        ),
        (
            InputDataModality.TOPOGRAPHY,
            products[2:],
            ["elevation profile analysis", "topographic context comparison"],
        ),
    ):
        available = all(
            p.valid_fraction >= config.minimum_valid_fraction for p in selected_products
        )
        first = selected_products[0]
        bounds = transform_bounds(
            CRS.from_wkt(first.derived_crs_wkt),
            CRS.from_string(f"+proj=longlat +R={RADIUS_M}"),
            -first.width_pixels * first.resolution_m / 2,
            -first.width_pixels * first.resolution_m / 2,
            first.width_pixels * first.resolution_m / 2,
            first.width_pixels * first.resolution_m / 2,
        )
        assets.append(
            DataAssetProfile(
                asset_id=f"{modality.value.lower()}-{row.id}",
                modality=modality,
                title=f"Verified derived {modality.value} product for {row.name}",
                source_uri=first.data_path,
                availability=AssetAvailability.AVAILABLE
                if available
                else AssetAvailability.UNAVAILABLE,
                data_format="GeoTIFF",
                spatial_resolution_m=first.resolution_m,
                spatial_coverage=SpatialCoverage(
                    minimum_longitude=bounds[0],
                    minimum_latitude=bounds[1],
                    maximum_longitude=bounds[2],
                    maximum_latitude=bounds[3],
                    longitude_direction="positive east",
                    latitude_type="planetocentric",
                ),
                model_representations=[p.preview_path for p in selected_products]
                + ([str(profile_path)] if modality is InputDataModality.TOPOGRAPHY else []),
                analytical_capabilities=capabilities,
                explanatory_capabilities=[
                    "surface appearance perspective"
                    if modality is InputDataModality.OPTICAL_IMAGE
                    else "topographic perspective"
                ],
                limitations=[
                    *limitations,
                    f"Minimum valid pixel fraction: "
                    f"{min(p.valid_fraction for p in selected_products):.6f}; "
                    f"preparation gate={config.minimum_valid_fraction}.",
                    "LOI values are display DN, not calibrated reflectance."
                    if modality is InputDataModality.OPTICAL_IMAGE
                    else "DEM scale/offset applied before reprojection; "
                    "resolution is not vertical accuracy.",
                ],
                estimated_cost=2,
            )
        )
    return PilotCase(
        catalogue=row,
        products=products,
        assets=assets,
        accepted=all(p.valid_fraction >= config.minimum_valid_fraction for p in products),
        limitations=limitations,
        profile_path=str(profile_path),
        overview_path=str(overview),
    )


def run_trials(case: PilotCase) -> list[SelectionTrial]:
    """Compare budgets and modality ablations using identical targets and fixed rules."""
    trials = []
    row = case.catalogue
    for question_type in CraterQuestionType:
        for condition, budget, excluded in (
            ("all-budget-5", 5, set()),
            ("limited-budget-3", 3, set()),
            ("without-topography", 5, {InputDataModality.TOPOGRAPHY}),
            ("without-image", 5, {InputDataModality.OPTICAL_IMAGE}),
        ):
            request = InputSelectionRequest(
                question=CraterQuestion(
                    question_id=f"{row.id}-{question_type.value}",
                    text=(
                        f"For {row.name}, propose investigations of crater morphology and "
                        f"possible formation or modification, with intent {question_type.value}."
                    ),
                    question_type=question_type,
                    crater=CraterReference(
                        crater_id=str(row.id),
                        name=row.name,
                        latitude=row.lat_n,
                        longitude=row.lon_e_0,
                        diameter_km=row.diameter,
                    ),
                ),
                assets=case.assets,
                constraints=InputSelectionConstraints(
                    maximum_modalities=3, maximum_total_cost=budget, forbidden_modalities=excluded
                ),
            )
            try:
                result = select_baseline(request)
                error = None
            except ValueError as exc:
                result = None
                error = str(exc)
            trials.append(
                SelectionTrial(
                    case_id=row.id,
                    condition=condition,
                    request=request,
                    result=result,
                    error=error,
                )
            )
    return trials


def write_report(run: PilotRun, root: Path) -> None:
    """Create a local review page with actual products and qualified selection results."""
    selections = Counter(
        (trial.condition, ", ".join(item.modality.value for item in trial.result.decision.selected))
        for trial in run.trials
        if trial.result is not None
    )
    table = "".join(
        f"<tr><td>{html.escape(condition)}</td><td>{html.escape(modalities)}</td><td>{count}</td></tr>"
        for (condition, modalities), count in sorted(selections.items())
    )
    cards = "".join(
        f"<section><h2>{html.escape(case.catalogue.name)} · {case.catalogue.diameter:g} km</h2>"
        f"<p>目录 ID {case.catalogue.id}；纬度 {case.catalogue.lat_n}°；"
        f"东经 {case.catalogue.lon_e_0}°；"
        f"有效像元比例：{', '.join(f'{p.valid_fraction:.2%}' for p in case.products)}；"
        f"准备检查：{'通过' if case.accepted else '未通过'}</p>"
        f'<img src="crater-{case.catalogue.id}/overview.png" alt="实际影像裁剪和高程剖面">'
        f'<p><a href="crater-{case.catalogue.id}/dem_local.png">高程图</a> · '
        f'<a href="crater-{case.catalogue.id}/east_west_profile.csv">剖面数值</a> · '
        f'<a href="crater-{case.catalogue.id}/catalogue.json">目录记录</a></p></section>'
        for case in run.cases
    )
    template = Template(Path(__file__).with_name("pilot_report.html").read_text(encoding="utf-8"))
    report = template.substitute(
        run_id=html.escape(run.run_id),
        pilot_version=html.escape(run.config.version),
        catalogue_rows=f"{run.catalogue_rows:,}",
        eligible_rows=run.eligible_rows,
        case_count=len(run.cases),
        accepted=sum(case.accepted for case in run.cases),
        trial_count=len(run.trials),
        failed_trials=sum(trial.error is not None for trial in run.trials),
        table=table,
        cards=cards,
    )
    with (root / "report.html").open("x", encoding="utf-8") as stream:
        stream.write(report)


def main() -> None:
    """Prepare the downloaded data and persist a new, reproducible pilot run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-count", type=int, default=12)
    args = parser.parse_args()
    config = PilotConfig(sample_count=args.sample_count)
    root = args.output.resolve()
    if "raw" in [part.lower() for part in root.parts] or root.exists():
        raise ValueError("output must be a new directory outside data/raw")
    records = load_sources(args.sources)
    by_id = {record.source.source_id: record for record in records}
    rows = load_catalogue(Path(by_id["herrick-2011-catalog"].path))
    targets, eligible = choose_targets(rows, config)
    root.mkdir(parents=True)
    cases = []
    trials = []
    for row in targets:
        print(f"Preparing {row.name} (ID {row.id}, {row.diameter} km)", flush=True)
        case = make_case(row, by_id, root, config)
        cases.append(case)
        with (root / f"crater-{row.id}" / "case.json").open("x", encoding="utf-8") as stream:
            stream.write(case.model_dump_json(indent=2))
        trials.extend(run_trials(case))
    run = PilotRun(
        run_id=root.name,
        created_utc=datetime.now(UTC),
        config=config,
        code_sha256={
            path.name: sha256_file(path)
            for path in Path(__file__).parent.iterdir()
            if path.suffix in (".py", ".html")
        },
        environment={
            "python": platform.python_version(),
            **{name: version(name) for name in ("numpy", "rasterio", "matplotlib", "pydantic")},
            "gdal": rasterio.__gdal_version__,
        },
        sources=records,
        catalogue_rows=len(rows),
        eligible_rows=eligible,
        sampling=(
            "Even diameter ranks from named targets, 50-150 km, abs(latitude)<45, "
            "15<abs(longitude)<150; no replacement after coverage failure."
        ),
        cases=cases,
        trials=trials,
        limitations=[
            CATALOGUE_LIMIT,
            "Only catalogue, optical image and topography enter selection; literature remains "
            "contextual documentation; simulation output not acquired.",
            "No LLM outputs, expert annotation or observed richness improvement.",
            "Hand-authored capabilities and ordinal costs; no automatic scientific quality score.",
            "2018 catalogue attachment blocked by publisher HTTP 403 challenge.",
            "Small convenience sample; no global population or causal conclusions.",
        ],
    )
    with (root / "run.json").open("x", encoding="utf-8") as stream:
        stream.write(run.model_dump_json(indent=2))
    write_report(run, root)
    print(f"Complete: {len(cases)} cases, {len(trials)} trials; {root / 'report.html'}", flush=True)


if __name__ == "__main__":
    main()
