"""Audit portable held-out evidence and freeze design separately from GPU approval."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path, PureWindowsPath
from typing import Literal

import numpy as np
import rasterio
from PIL import Image
from pydantic import Field
from rasterio.warp import transform

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import QuestionSet
from autonomous_modality.heldout import Cohort, write_new
from autonomous_modality.heldout_protocol import COSTS, Design, FrozenProtocol, freeze_design
from autonomous_modality.models import StrictModel
from autonomous_modality.multispectral import MultispectralPackage, summarize_multispectral
from autonomous_modality.multispectral_acquisition import GEO
from autonomous_modality.multispectral_dataset import (
    WAVELENGTHS,
    FourModalityManifest,
    four_modality_loader,
    masks,
)
from autonomous_modality.multispectral_release import MODALITIES, Reviews, validate_reviews
from autonomous_modality.pilot import CatalogueRow

COMPACT_IMAGES = (
    "optical_local.png",
    "optical_context.png",
    "elevation.png",
    "profile_east.png",
    "profile_north.png",
)


class CompactReceipt(StrictModel):
    version: Literal["four-modality-compact-1.0"]
    source_sha256: dict[str, str]
    implementation_sha256: dict[str, str]
    image_edge: Literal[448]
    output_sha256: dict[str, str]


class TargetAudit(StrictModel):
    case_id: int
    name: str
    local_valid_fraction: float
    context_valid_fraction: float
    context_missing_pixels: int
    region_count: Literal[4] = 4
    bands: Literal[8] = 8
    evidence_images: dict[str, int]
    summary_recomputed: Literal[True] = True
    masks_recomputed: Literal[True] = True
    terrain_profiles_recomputed: Literal[True] = True
    fine_registration_verified: Literal[False] = False


class HeldoutRelease(StrictModel):
    version: Literal["heldout-four-modality-release-1.0"] = "heldout-four-modality-release-1.0"
    status: Literal["data_and_design_frozen_runtime_pending"] = (
        "data_and_design_frozen_runtime_pending"
    )
    split: Literal["held_out_from_model_development"] = "held_out_from_model_development"
    data_complete: Literal[True] = True
    model_inference_performed: Literal[False] = False
    expert_approved: Literal[False] = False
    runtime_approved: Literal[False] = False
    cases: list[TargetAudit] = Field(min_length=30, max_length=30)
    files: dict[str, str]


def verify_files(root: Path, files: dict[str, str]) -> None:
    """Reject missing, modified, absolute and escaping file references."""
    for name, digest in files.items():
        relative = Path(name)
        path = (root / relative).resolve()
        if (
            relative.is_absolute()
            or PureWindowsPath(name).drive
            or ".." in name.replace("\\", "/").split("/")
            or not path.is_relative_to(root.resolve())
        ):
            raise ValueError("UNSAFE_RELEASE_PATH")
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"RELEASE_FILE_CHANGED: {name}")


def verify_compact(root: Path, compact: Path) -> None:
    """Validate fixed image inventory, source linkage and all compact output hashes."""
    receipt = CompactReceipt.model_validate_json((compact / "receipt.json").read_bytes())
    manifest = FourModalityManifest.model_validate_json((root / "manifest.json").read_bytes())
    expected = {*COMPACT_IMAGES, "terrain.txt", "multispectral.txt"}
    if set(receipt.output_sha256) != expected or receipt.source_sha256 != manifest.files:
        raise ValueError("COMPACT_INVENTORY_OR_SOURCE_MISMATCH")
    verify_files(root, receipt.source_sha256)
    verify_files(compact, receipt.output_sha256)
    for name in COMPACT_IMAGES:
        with Image.open(compact / name) as image:
            if max(image.size) != receipt.image_edge:
                raise ValueError("COMPACT_IMAGE_SIZE_CHANGED")


def verify_profiles(root: Path) -> None:
    """Recompute both central profiles from the DEM and compare ordered CSV samples."""
    with rasterio.open(root / "dem_numeric.tif") as ds:
        data = ds.read(1, masked=True).astype(float).filled(np.nan)
        data = data * ds.scales[0] + ds.offsets[0]
        affine = ds.transform
        for axis, lines, step, origin in (
            ("east", data, affine.a, affine.c),
            ("north", data.T, affine.e, affine.f),
        ):
            n = len(lines)
            values = lines[n // 2] if n % 2 else (lines[n // 2 - 1] + lines[n // 2]) / 2
            distances = (origin + (np.arange(len(values)) + 0.5) * step) / 1000
            order = np.argsort(distances)
            with (root / f"profile_{axis}.csv").open(newline="", encoding="utf-8") as stream:
                reader = csv.reader(stream)
                header = next(reader)
                if header != [f"{axis}_from_catalogue_centre_km", "elevation_m"]:
                    raise ValueError("PROFILE_HEADER_MISMATCH")
                rows = list(reader)
            actual = np.array([[float(x), float(y) if y else np.nan] for x, y in rows])
            expected = np.column_stack((distances[order], values[order]))
            if actual.shape != expected.shape or not np.allclose(actual, expected, equal_nan=True):
                raise ValueError("PROFILE_VALUE_MISMATCH")


def audit_target(root: Path, case_id: int, diameter: float) -> TargetAudit:
    """Recompute spectral statistics, masks, coverage and evidence-route image counts."""
    manifest = FourModalityManifest.model_validate_json((root / "manifest.json").read_bytes())
    if manifest.case_id != case_id or not manifest.technical_pass:
        raise ValueError("TARGET_ID_OR_QA_MISMATCH")
    verify_files(root, manifest.files)
    catalogue = CatalogueRow.model_validate_json((root / "core_views/catalogue.json").read_bytes())
    if catalogue.id != case_id or catalogue.name != manifest.name or catalogue.diameter != diameter:
        raise ValueError("CATALOGUE_IDENTITY_MISMATCH")
    for coverage in (manifest.local, manifest.context):
        x, y = transform(GEO, coverage.crs_wkt, [catalogue.lon_e_0], [catalogue.lat_n])
        if math.hypot(x[0], y[0]) > 1:
            raise ValueError("TARGET_GRID_CENTER_MISMATCH")
    if {a.modality.value: a.estimated_cost for a in manifest.assets} != COSTS:
        raise ValueError("ASSET_COST_MISMATCH")
    verify_profiles(root / "core_views")
    if len(manifest.assets) != 4 or {a.modality for a in manifest.assets} != MODALITIES:
        raise ValueError("MODALITY_INVENTORY_MISMATCH")
    spectral = MultispectralPackage.model_validate_json((root / "summary.json").read_bytes())
    if (
        spectral.metadata.case_id != str(case_id)
        or spectral.metadata.provenance_kind != "observed"
        or [b.wavelength_nm for b in spectral.metadata.bands] != WAVELENGTHS
        or len(spectral.regions) != 4
    ):
        raise ValueError("SPECTRAL_IDENTITY_MISMATCH")
    if summarize_multispectral(root / "multispectral.npz", spectral.metadata) != spectral:
        raise ValueError("SPECTRAL_SUMMARY_MISMATCH")
    with np.load(root / "multispectral.npz", allow_pickle=False) as data:
        expected = masks(manifest.context, diameter)
        if {key for key in data.files if key.startswith("roi_")} != set(expected):
            raise ValueError("REGION_SET_MISMATCH")
        for key, mask in expected.items():
            if not np.array_equal(mask, data[key]):
                raise ValueError("REGION_MASK_MISMATCH")
        cube = data["reflectance"]
        missing = int((~np.isfinite(cube).all(axis=0)).sum())
        if np.any(np.isfinite(cube).any(axis=0) & (data["source_image_count"] <= 0)):
            raise ValueError("ZERO_COUNT_WITH_VALID_REFLECTANCE")
        with rasterio.open(root / "multispectral_context.tif") as ds:
            if not np.array_equal(ds.read(), cube, equal_nan=True):
                raise ValueError("NPZ_GEOTIFF_MISMATCH")
    for filename, coverage in [
        ("multispectral_local.tif", manifest.local),
        ("multispectral_context.tif", manifest.context),
    ]:
        with rasterio.open(root / filename) as ds:
            values = ds.read()
            if (
                ds.count != 8
                or ds.width != coverage.width
                or ds.height != coverage.height
                or ds.crs != rasterio.crs.CRS.from_wkt(coverage.crs_wkt)
                or not np.allclose(list(ds.transform), coverage.transform)
                or not np.isclose(
                    np.isfinite(values).all(axis=0).mean(), coverage.joint_valid_fraction
                )
                or coverage.joint_valid_fraction < 0.95
            ):
                raise ValueError("SPECTRAL_GRID_OR_COVERAGE_MISMATCH")
    counts = {}
    loader = four_modality_loader(root)
    for modality in sorted(MODALITIES):
        observation = loader(modality)
        if observation.modality != modality or not observation.blocks:
            raise ValueError("INVALID_EVIDENCE_ROUTE")
        counts[modality.value] = sum(block.type == "image" for block in observation.blocks)
    if counts != {
        "CRATER_CATALOG": 0,
        "OPTICAL_IMAGE": 2,
        "TOPOGRAPHY": 3,
        "MULTISPECTRAL_IMAGE": 0,
    }:
        raise ValueError("WRONG_MODEL_REPRESENTATION")
    return TargetAudit(
        case_id=case_id,
        name=manifest.name,
        local_valid_fraction=manifest.local.joint_valid_fraction,
        context_valid_fraction=manifest.context.joint_valid_fraction,
        context_missing_pixels=missing,
        evidence_images=counts,
    )


def finalize(root: Path, reviews_path: Path, project: Path) -> HeldoutRelease:
    """Freeze new artifacts only after complete QA; retain explicit runtime prerequisites."""
    if (root / "release.json").exists() or (root / "frozen").exists():
        raise FileExistsError("Dataset already finalized or freeze attempt exists")
    cohort = Cohort.model_validate_json((root / "cohort.json").read_bytes())
    reviews = Reviews.model_validate_json(reviews_path.read_bytes())
    validate_reviews(reviews, [t.id for t in cohort.targets])
    audits = []
    for target in cohort.targets:
        audits.append(audit_target(root / f"crater-{target.id}", target.id, target.diameter))
        compact = root / "model_inputs" / f"crater-{target.id}"
        verify_compact(root / f"crater-{target.id}", compact)
    frozen = root / "frozen"
    frozen.mkdir()
    copies = {
        "questions.json": project / "configs/mercury_questions_v1.json",
        "rubric.md": project / "docs/heldout_rubric_v1.md",
        "protocol_implementation.py": project / "src/autonomous_modality/heldout_protocol.py",
        "selector_and_answer_prompts.py": project / "src/autonomous_modality/development_inputs.py",
        "iterative.py": project / "src/autonomous_modality/iterative.py",
        "notebook.ipynb": project / "notebooks/autonomous_modality_selection_four_modality.ipynb",
        "core_builder.py": project
        / "extensions/evidence_views_v1/src/ams_evidence_views/builder.py",
        "multispectral_dataset.py": project / "src/autonomous_modality/multispectral_dataset.py",
        "multispectral_acquisition.py": project
        / "src/autonomous_modality/multispectral_acquisition.py",
        "compact_adapter.py": project / "src/autonomous_modality/colab_four_modality.py",
        "heldout_builder.py": project / "src/autonomous_modality/heldout_release.py",
        "heldout_finalize.py": Path(__file__),
    }
    for name, source in copies.items():
        shutil.copyfile(source, frozen / name)
    for source_root, destination in [
        (project / "src/autonomous_modality", frozen / "code/autonomous_modality"),
        (
            project / "extensions/evidence_views_v1/src/ams_evidence_views",
            frozen / "code/ams_evidence_views",
        ),
    ]:
        destination.mkdir(parents=True)
        for source in sorted(source_root.glob("*.py")):
            shutil.copyfile(source, destination / source.name)
    shutil.copyfile(project / "pyproject.toml", frozen / "pyproject.toml")
    questions = QuestionSet.model_validate_json((frozen / "questions.json").read_bytes())
    design = freeze_design(cohort, questions)
    write_new(frozen / "design.json", design)
    protocol = FrozenProtocol(
        question_sha256=sha256_file(frozen / "questions.json"),
        cohort_sha256=sha256_file(root / "cohort.json"),
        pinned_files={
            p.relative_to(frozen).as_posix(): sha256_file(p)
            for p in sorted(frozen.rglob("*"))
            if p.is_file()
        },
    )
    write_new(frozen / "protocol.json", protocol)
    shutil.copyfile(reviews_path, root / "spectral_reviews.json")
    release = HeldoutRelease(
        cases=audits,
        files={
            str(p.relative_to(root)).replace("\\", "/"): sha256_file(p)
            for p in sorted(root.rglob("*"))
            if p.is_file()
        },
    )
    write_new(root / "release.json", release)
    verify_files(root, release.files)
    return release


def verify_release(root: Path) -> HeldoutRelease:
    """Verify an existing portable release and its reproducible design without inference."""
    release = HeldoutRelease.model_validate_json((root / "release.json").read_bytes())
    required = {
        "cohort.json",
        "core_reviews.json",
        "spectral_reviews.json",
        "frozen/protocol.json",
        "frozen/design.json",
        "frozen/questions.json",
    }
    if not required.issubset(release.files):
        raise ValueError("INCOMPLETE_RELEASE_INVENTORY")
    verify_files(root, release.files)
    cohort = Cohort.model_validate_json((root / "cohort.json").read_bytes())
    ids = [t.id for t in cohort.targets]
    if [c.case_id for c in release.cases] != ids:
        raise ValueError("RELEASE_TARGET_SET_MISMATCH")
    for name in ("core_reviews.json", "spectral_reviews.json"):
        validate_reviews(Reviews.model_validate_json((root / name).read_bytes()), ids)
    frozen = root / "frozen"
    protocol = FrozenProtocol.model_validate_json((frozen / "protocol.json").read_bytes())
    verify_files(frozen, protocol.pinned_files)
    if protocol.cohort_sha256 != sha256_file(
        root / "cohort.json"
    ) or protocol.question_sha256 != sha256_file(frozen / "questions.json"):
        raise ValueError("FROZEN_IDENTITY_MISMATCH")
    questions = QuestionSet.model_validate_json((frozen / "questions.json").read_bytes())
    design = Design.model_validate_json((frozen / "design.json").read_bytes())
    if freeze_design(cohort, questions) != design:
        raise ValueError("SHARED_DESIGN_MISMATCH")
    for target in cohort.targets:
        package = root / f"crater-{target.id}"
        manifest = FourModalityManifest.model_validate_json(
            (package / "manifest.json").read_bytes()
        )
        required_case = {
            f"crater-{target.id}/manifest.json",
            f"model_inputs/crater-{target.id}/receipt.json",
        }
        required_case.update(f"crater-{target.id}/{name}" for name in manifest.files)
        required_case.update(
            f"model_inputs/crater-{target.id}/{name}"
            for name in (*COMPACT_IMAGES, "terrain.txt", "multispectral.txt")
        )
        if not required_case.issubset(release.files):
            raise ValueError("INCOMPLETE_TARGET_INVENTORY")
        verify_compact(package, root / "model_inputs" / f"crater-{target.id}")
    return release


def main() -> None:
    """Finalize once or verify a release; never run a model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    release = (
        finalize(args.root, args.reviews, args.project)
        if args.reviews
        else verify_release(args.root)
    )
    print(
        json.dumps(
            {
                "status": release.status,
                "targets": len(release.cases),
                "verified_files": len(release.files),
            }
        )
    )


if __name__ == "__main__":
    main()
