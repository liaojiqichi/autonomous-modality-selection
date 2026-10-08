"""Build held-out four-modality inputs separately from historical development releases."""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime
from pathlib import Path

from autonomous_modality.acquisition import DownloadRecord, sha256_file
from autonomous_modality.benchmark import VisualReview, audit_case, build_package, verify_package
from autonomous_modality.colab_four_modality import prepare_compact_inputs
from autonomous_modality.heldout import Cohort, PreparationReport, write_new
from autonomous_modality.multispectral_acquisition import (
    AcquisitionPlan,
    Receipt,
    TargetPlan,
    intersects,
    parse_tile,
)
from autonomous_modality.multispectral_dataset import prepare_target
from autonomous_modality.multispectral_release import Reviews, validate_reviews
from autonomous_modality.pilot import PilotCase


def build(
    candidate: Path, sources: Path, cache: Path, reviews_path: Path, workspace: Path, output: Path
) -> None:
    """Verify core crops, build both profiles, spectral products and 448-pixel inputs."""
    from ams_evidence_views.builder import build_package as build_views

    if output.exists() or workspace.exists():
        raise FileExistsError("Use new workspace and output directories")
    cohort_path = candidate / "cohort.json"
    cohort = Cohort.model_validate_json(cohort_path.read_bytes())
    preparation = PreparationReport.model_validate_json(
        (candidate / "preparation.json").read_bytes()
    )
    if sha256_file(cohort_path) != preparation.cohort_sha256:
        raise ValueError("COHORT_CHANGED")
    if [t.case_id for t in preparation.targets] != [t.id for t in cohort.targets]:
        raise ValueError("TARGET_SET_CHANGED")
    reviews = Reviews.model_validate_json(reviews_path.read_bytes())
    validate_reviews(reviews, [r.id for r in cohort.targets])
    records = []
    for path in sorted(sources.glob("*.provenance.json")):
        record = DownloadRecord.model_validate_json(path.read_bytes())
        real = sources / record.source.filename
        if real.stat().st_size != record.bytes or sha256_file(real) != record.sha256:
            raise ValueError("SOURCE_CHANGED")
        records.append(record)
    tiles = []
    for label in sorted(cache.glob("MDIS_MDR_064PPD_H*[NS][EW]4.LBL")):
        receipt = Receipt.model_validate_json(label.with_suffix(".LBL.receipt.json").read_bytes())
        if sha256_file(label) != receipt.sha256:
            raise ValueError("LABEL_CHANGED")
        tile = parse_tile(label, receipt.url)
        if not any(intersects(entry.context_bounds, tile) for entry in preparation.targets):
            continue
        image = label.with_suffix(".IMG")
        rec = Receipt.model_validate_json(image.with_suffix(".IMG.receipt.json").read_bytes())
        if (
            rec.url != tile.url
            or image.stat().st_size != tile.expected_bytes
            or sha256_file(image) != rec.sha256
        ):
            raise ValueError("SOURCE_TILE_CHANGED")
        tiles.append(tile)
    workspace.mkdir(parents=True)
    output.mkdir(parents=True)
    shutil.copyfile(cohort_path, output / "cohort.json")
    shutil.copyfile(reviews_path, output / "core_reviews.json")
    targets = []
    for entry in preparation.targets:
        source = candidate / "core-crops"
        case_path = source / f"crater-{entry.case_id}" / "case.json"
        if sha256_file(case_path) != entry.case_sha256:
            raise ValueError("CORE_CASE_CHANGED")
        case = PilotCase.model_validate_json(case_path.read_bytes())
        reviewed = next(r for r in reviews.reviews if r.case_id == entry.case_id)
        review = VisualReview(
            case_id=entry.case_id,
            status=reviewed.status,
            observation=reviewed.observation,
            concern=reviewed.limitations,
            reviewer="Codex visual screening; not a planetary-science expert",
            evidence_files=["overview.png", "dem_local.png"],
        )
        audit = audit_case(case, source, review, records)
        if audit.technical_errors:
            raise ValueError(f"CORE_AUDIT_FAILED: {entry.case_id}: {audit.technical_errors}")
        base = workspace / "core-packages" / f"crater-{entry.case_id}"
        package = build_package(case, audit, source, base)
        write_new(base / "audit.json", audit)
        views = workspace / "views" / f"crater-{entry.case_id}"
        build_views(base, views)
        targets.append(
            TargetPlan(
                case_id=entry.case_id,
                name=entry.name,
                package_path=str((base / "package.json").resolve()),
                package_sha256=sha256_file(base / "package.json"),
                longitude_east=package.case.lon_e_0,
                latitude=package.case.lat_n,
                diameter_km=package.case.diameter,
                context_bounds=entry.context_bounds,
                tiles=[t.product_id for t in tiles if intersects(entry.context_bounds, t)],
            )
        )
        print(f"Core views verified: {entry.name}", flush=True)
    plan = AcquisitionPlan(
        created_utc=datetime.now(UTC).isoformat(),
        source_audit=str((candidate / "preparation.json").resolve()),
        source_audit_sha256=sha256_file(candidate / "preparation.json"),
        targets=targets,
        tiles=tiles,
    )
    plan_path = output / "acquisition_plan.json"
    write_new(plan_path, plan)
    for target in targets:
        prepare_target(target, plan, plan_path, workspace / "views", output)
        prepare_compact_inputs(
            output / f"crater-{target.case_id}",
            output / "model_inputs" / f"crater-{target.case_id}",
            448,
        )
        print(f"Four-modality inputs built: {target.name}", flush=True)


def main() -> None:
    """Build all allocated cases offline from explicit reviewed inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-core", action="store_true")
    for name in ("candidate", "sources", "cache", "reviews", "workspace", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.reuse_core:
        complete_spectral(args.candidate, args.cache, args.reviews, args.workspace, args.output)
    else:
        build(args.candidate, args.sources, args.cache, args.reviews, args.workspace, args.output)


def complete_spectral(
    candidate: Path, cache: Path, reviews_path: Path, workspace: Path, output: Path
) -> None:
    """Reuse verified core artifacts and recompute all tile matches after wraparound fix."""
    from ams_evidence_views.adapter import load_package

    if output.exists():
        raise FileExistsError(output)
    cohort = Cohort.model_validate_json((candidate / "cohort.json").read_bytes())
    preparation = PreparationReport.model_validate_json(
        (candidate / "preparation.json").read_bytes()
    )
    if sha256_file(candidate / "cohort.json") != preparation.cohort_sha256:
        raise ValueError("COHORT_CHANGED")
    reviews = Reviews.model_validate_json(reviews_path.read_bytes())
    validate_reviews(reviews, [row.id for row in cohort.targets])
    tiles = []
    for label in sorted(cache.glob("MDIS_MDR_064PPD_H*[NS][EW]4.LBL")):
        rec = Receipt.model_validate_json(label.with_suffix(".LBL.receipt.json").read_bytes())
        if sha256_file(label) != rec.sha256:
            raise ValueError("LABEL_CHANGED")
        tile = parse_tile(label, rec.url)
        if any(intersects(t.context_bounds, tile) for t in preparation.targets):
            image = label.with_suffix(".IMG")
            receipt = Receipt.model_validate_json(
                image.with_suffix(".IMG.receipt.json").read_bytes()
            )
            if (
                receipt.url != tile.url
                or image.stat().st_size != tile.expected_bytes
                or sha256_file(image) != receipt.sha256
            ):
                raise ValueError("SOURCE_TILE_CHANGED")
            tiles.append(tile)
    targets = []
    for row in cohort.targets:
        base = workspace / "core-packages" / f"crater-{row.id}"
        package = verify_package(base)
        if package.case != row:
            raise ValueError("CORE_TARGET_CHANGED")
        view = load_package(workspace / "views" / f"crater-{row.id}")
        if view.source_package_sha256 != sha256_file(base / "package.json"):
            raise ValueError("CORE_VIEWS_CHANGED")
        entry = next(t for t in preparation.targets if t.case_id == row.id)
        targets.append(
            TargetPlan(
                case_id=row.id,
                name=row.name,
                package_path=str((base / "package.json").resolve()),
                package_sha256=sha256_file(base / "package.json"),
                longitude_east=row.lon_e_0,
                latitude=row.lat_n,
                diameter_km=row.diameter,
                context_bounds=entry.context_bounds,
                tiles=[t.product_id for t in tiles if intersects(entry.context_bounds, t)],
            )
        )
    output.mkdir(parents=True)
    shutil.copyfile(candidate / "cohort.json", output / "cohort.json")
    shutil.copyfile(reviews_path, output / "core_reviews.json")
    plan = AcquisitionPlan(
        created_utc=datetime.now(UTC).isoformat(),
        source_audit=str((candidate / "preparation.json").resolve()),
        source_audit_sha256=sha256_file(candidate / "preparation.json"),
        targets=targets,
        tiles=tiles,
    )
    plan_path = output / "acquisition_plan.json"
    write_new(plan_path, plan)
    for target in targets:
        manifest = prepare_target(target, plan, plan_path, workspace / "views", output)
        if not manifest.technical_pass:
            raise ValueError(f"MULTISPECTRAL_COVERAGE_FAILED: {target.case_id}")
        prepare_compact_inputs(
            output / f"crater-{target.case_id}",
            output / "model_inputs" / f"crater-{target.case_id}",
            448,
        )
        print(f"Four-modality inputs built: {target.name}", flush=True)


if __name__ == "__main__":
    main()
