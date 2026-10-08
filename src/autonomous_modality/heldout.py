"""Offline candidate test-set preparation; no model calls or scientific approval."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Literal, Self

import rasterio
from pydantic import Field, model_validator
from rasterio.warp import transform_bounds

from autonomous_modality.acquisition import DownloadRecord, sha256_file
from autonomous_modality.models import StrictModel
from autonomous_modality.multispectral_acquisition import GEO, Receipt, intersects, parse_tile
from autonomous_modality.pilot import CatalogueRow, PilotConfig, load_catalogue, make_case

# All twelve previously inspected pilot targets (including holds), plus Caloris.
EXCLUDED_IDS = (734, 858, 908, 1153, 1695, 1851, 2179, 4512, 4870, 5031, 6611, 16604, 19610)


class Cohort(StrictModel):
    """Candidate allocation, pending technical review and protocol freezing."""

    version: Literal["heldout-candidates-1.0"] = "heldout-candidates-1.0"
    seed: int = 20261008
    catalogue_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    excluded_ids: list[int]
    targets: list[CatalogueRow] = Field(min_length=30, max_length=30)
    reserves: list[CatalogueRow]
    status: Literal["candidate_pending_review"] = "candidate_pending_review"
    selection_rule: str = (
        "Named targets; diameter 50-150 km inclusive; abs(latitude)<45; "
        "15<abs(longitude)<150; exclude historical IDs and Caloris. "
        "Sort by SHA256(seed:id), select first 30; retain remainder as ordered reserves. "
        "Selection does not depend on cached coverage, images or model outcomes."
    )
    llm_called: Literal[False] = False
    ready_for_evaluation: Literal[False] = False

    @model_validator(mode="after")
    def check_ids(self) -> Self:
        """Prevent duplicate targets and historical contamination."""
        ids = [row.id for row in [*self.targets, *self.reserves]]
        if len(ids) != len(set(ids)) or set(ids) & set(self.excluded_ids):
            raise ValueError("DUPLICATE_OR_EXCLUDED_TARGET")
        if not set(EXCLUDED_IDS).issubset(self.excluded_ids):
            raise ValueError("MISSING_HISTORICAL_EXCLUSIONS")
        return self


def select_cohort(rows: list[CatalogueRow], checksum: str, seed: int = 20261008) -> Cohort:
    """Allocate candidates without inspecting target images or model responses."""
    if len({row.id for row in rows}) != len(rows):
        raise ValueError("DUPLICATE_CATALOGUE_ID")
    pool = [
        r
        for r in rows
        if r.id not in EXCLUDED_IDS
        and r.name.strip()
        and 50 <= r.diameter <= 150
        and abs(r.lat_n) < 45
        and 15 < abs(r.lon_e_0) < 150
    ]
    pool.sort(key=lambda r: (hashlib.sha256(f"{seed}:{r.id}".encode()).hexdigest(), r.id))
    return Cohort(
        seed=seed,
        catalogue_sha256=checksum,
        excluded_ids=list(EXCLUDED_IDS),
        targets=pool[:30],
        reserves=pool[30:],
    )


class PreparedTarget(StrictModel):
    """Actual core crops and outstanding multispectral source requirements."""

    case_id: int
    name: str
    case_sha256: str
    core_coverage_pass: bool
    context_bounds: list[float]
    required_tiles: list[str]
    missing_tiles: list[str]
    missing_source_bytes: int = Field(ge=0)
    visual_review: Literal["pending"] = "pending"
    multispectral_crops: Literal["pending"] = "pending"
    model_input_package: Literal["pending"] = "pending"
    ready_for_evaluation: Literal[False] = False


class PreparationReport(StrictModel):
    """Preparation checkpoint, not a final benchmark release."""

    cohort_sha256: str
    implementation_sha256: str
    targets: list[PreparedTarget]
    missing_tiles: list[str]
    missing_source_bytes: int
    ready_for_evaluation: Literal[False] = False
    llm_called: Literal[False] = False


def write_new(path: Path, value: StrictModel) -> None:
    """Persist without replacing historical work."""
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value.model_dump_json(indent=2))


def prepare(sources: Path, cache: Path, output: Path) -> PreparationReport:
    """Reuse verified cached products; create core crops and acquisition requirements."""
    if output.exists():
        raise FileExistsError(output)
    records = {}
    for path in sorted(sources.glob("*.provenance.json")):
        record = DownloadRecord.model_validate_json(path.read_bytes())
        source = sources / record.source.filename
        if source.stat().st_size != record.bytes or sha256_file(source) != record.sha256:
            raise ValueError("SOURCE_CHECKSUM_MISMATCH")
        records[record.source.source_id] = record.model_copy(update={"path": str(source.resolve())})
    catalogue = records["herrick-2011-catalog"]
    cohort = select_cohort(load_catalogue(Path(catalogue.path)), catalogue.sha256)
    labels = sorted(cache.glob("MDIS_MDR_064PPD_H*[NS][EW]4.LBL"))
    expected = {
        f"MDIS_MDR_064PPD_H{h:02d}{q}4" for h in range(2, 15) for q in ("NE", "NW", "SE", "SW")
    }
    if {p.stem for p in labels} != expected:
        raise ValueError("INCOMPLETE_NONPOLAR_LABEL_INVENTORY")
    tiles, available = [], set()
    for label in labels:
        receipt = Receipt.model_validate_json(label.with_suffix(".LBL.receipt.json").read_bytes())
        if sha256_file(label) != receipt.sha256:
            raise ValueError("LABEL_CHECKSUM_MISMATCH")
        tile = parse_tile(label, receipt.url)
        tiles.append(tile)
        image = label.with_suffix(".IMG")
        if image.exists():
            rec = Receipt.model_validate_json(image.with_suffix(".IMG.receipt.json").read_bytes())
            if (
                rec.url != tile.url
                or image.stat().st_size != tile.expected_bytes
                or sha256_file(image) != rec.sha256
            ):
                raise ValueError("TILE_CHECKSUM_MISMATCH")
            available.add(tile.product_id)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "cohort.json", cohort)
    root = output / "core-crops"
    root.mkdir()
    entries = []
    for row in cohort.targets:
        case = make_case(row, records, root, PilotConfig())
        path = root / f"crater-{row.id}" / "case.json"
        write_new(path, case)
        with rasterio.open(path.parent / "image_context.tif") as ds:
            bounds = list(transform_bounds(ds.crs, GEO, *ds.bounds, densify_pts=41))
        needed = [t for t in tiles if intersects(bounds, t)]
        if not needed:
            raise ValueError("NO_INTERSECTING_TILE")
        missing = [t for t in needed if t.product_id not in available]
        entry = PreparedTarget(
            case_id=row.id,
            name=row.name,
            case_sha256=sha256_file(path),
            core_coverage_pass=case.accepted,
            context_bounds=bounds,
            required_tiles=[t.product_id for t in needed],
            missing_tiles=[t.product_id for t in missing],
            missing_source_bytes=sum(t.expected_bytes for t in missing),
        )
        write_new(path.parent / "preparation.json", entry)
        entries.append(entry)
        print(
            f"Prepared {row.name}: core_pass={case.accepted}, missing_tiles={len(missing)}",
            flush=True,
        )
    missing_ids = sorted({t for entry in entries for t in entry.missing_tiles})
    report = PreparationReport(
        cohort_sha256=sha256_file(output / "cohort.json"),
        implementation_sha256=sha256_file(Path(__file__)),
        targets=entries,
        missing_tiles=missing_ids,
        missing_source_bytes=sum(t.expected_bytes for t in tiles if t.product_id in missing_ids),
    )
    write_new(output / "preparation.json", report)
    return report


def main() -> None:
    """Run offline candidate preparation; never call an LLM."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--multispectral-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.sources, args.multispectral_cache, args.output)
    print(
        f"Prepared {len(report.targets)} candidates; missing bytes: {report.missing_source_bytes}"
    )


if __name__ == "__main__":
    main()
