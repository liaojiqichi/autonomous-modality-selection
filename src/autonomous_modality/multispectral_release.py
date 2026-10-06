"""Release verification and recorded visual correspondence review, without inference."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from pydantic import Field

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import verify_package
from autonomous_modality.models import InputDataModality, NonEmptyString, StrictModel
from autonomous_modality.multispectral import MultispectralPackage
from autonomous_modality.multispectral_acquisition import AcquisitionPlan, write_new
from autonomous_modality.multispectral_dataset import FourModalityManifest, four_modality_loader

MODALITIES = {
    InputDataModality.CRATER_CATALOG,
    InputDataModality.OPTICAL_IMAGE,
    InputDataModality.TOPOGRAPHY,
    InputDataModality.MULTISPECTRAL_IMAGE,
}


class Review(StrictModel):
    case_id: int
    status: Literal["provisional_pass", "hold"]
    observation: NonEmptyString
    limitations: NonEmptyString


class Reviews(StrictModel):
    reviewer: NonEmptyString
    expert_approved: Literal[False] = False
    reviews: list[Review] = Field(min_length=1)


class ReleaseCase(StrictModel):
    case_id: int
    name: str
    package: str
    local_valid_fraction: float
    context_valid_fraction: float
    context_missing_pixels: int
    radiance_factor_min: float
    radiance_factor_max: float
    reviewed: Review
    routed_modalities: list[InputDataModality]


class Release(StrictModel):
    version: Literal["mercury-four-modality-release-1.0"] = "mercury-four-modality-release-1.0"
    created_utc: str
    status: Literal["complete_development_dataset"] = "complete_development_dataset"
    split: Literal["previously_inspected_development"] = "previously_inspected_development"
    reviewer: str
    expert_approved: Literal[False] = False
    measured_subpixel_registration: Literal[False] = False
    inference_performed: Literal[False] = False
    original_packages_verified_unchanged: bool
    environment: dict[str, str]
    cases: list[ReleaseCase]
    files: dict[str, str]


def validate_reviews(reviews: Reviews, case_ids: list[int]) -> None:
    """Require one passing recorded review for each target, without silent omissions."""
    ids = [r.case_id for r in reviews.reviews]
    if len(ids) != len(set(ids)) or set(ids) != set(case_ids):
        raise ValueError("REVIEW_TARGET_SET_MISMATCH")
    if any(r.status != "provisional_pass" for r in reviews.reviews):
        raise ValueError("REVIEW_HOLD_PREVENTS_COMPLETE_RELEASE")


def finalize(root: Path, reviews: Reviews) -> Release:
    """Verify real packages, evidence routing, original hashes and review completeness."""
    plan = AcquisitionPlan.model_validate_json((root / "acquisition_plan.json").read_bytes())
    validate_reviews(reviews, [t.case_id for t in plan.targets])
    cases = []
    for target in plan.targets:
        package_root = root / f"crater-{target.case_id}"
        manifest = FourModalityManifest.model_validate_json(
            (package_root / "manifest.json").read_bytes()
        )
        if {a.modality for a in manifest.assets} != MODALITIES or len(manifest.assets) != 4:
            raise ValueError("FOUR_MODALITY_INVENTORY_MISMATCH")
        original = verify_package(Path(target.package_path).parent)
        if sha256_file(Path(target.package_path)) != target.package_sha256:
            raise ValueError("ORIGINAL_PACKAGE_CHANGED")
        catalogue = json.loads((package_root / "core_views/catalogue.json").read_text())
        if catalogue != original.case.model_dump(mode="json") or manifest.case_id != target.case_id:
            raise ValueError("CATALOGUE_IDENTITY_MISMATCH")
        spectral = MultispectralPackage.model_validate_json(
            (package_root / "summary.json").read_bytes()
        )
        if (
            spectral.metadata.case_id != str(target.case_id)
            or spectral.metadata.provenance_kind != "observed"
            or len(spectral.metadata.bands) != 8
        ):
            raise ValueError("SPECTRAL_IDENTITY_MISMATCH")
        loader = four_modality_loader(package_root)
        for modality in sorted(MODALITIES):
            observation = loader(modality)
            if observation.modality != modality or not observation.blocks:
                raise ValueError("EVIDENCE_ROUTING_FAILED")
        with np.load(package_root / "multispectral.npz", allow_pickle=False) as data:
            cube = data["reflectance"]
            missing = int((~np.isfinite(cube).all(axis=0)).sum())
            minimum, maximum = float(np.nanmin(cube)), float(np.nanmax(cube))
        cases.append(
            ReleaseCase(
                case_id=target.case_id,
                name=target.name,
                package=f"crater-{target.case_id}/manifest.json",
                local_valid_fraction=manifest.local.joint_valid_fraction,
                context_valid_fraction=manifest.context.joint_valid_fraction,
                context_missing_pixels=missing,
                radiance_factor_min=minimum,
                radiance_factor_max=maximum,
                reviewed=next(r for r in reviews.reviews if r.case_id == target.case_id),
                routed_modalities=sorted(MODALITIES),
            )
        )
    write_new(root / "visual_reviews.json", reviews)
    release = Release(
        created_utc=datetime.now(UTC).isoformat(),
        reviewer=reviews.reviewer,
        original_packages_verified_unchanged=True,
        environment={
            "python": platform.python_version(),
            "numpy": np.__version__,
            "rasterio": rasterio.__version__,
        },
        cases=cases,
        files={
            str(p.relative_to(root)).replace("\\", "/"): sha256_file(p)
            for p in sorted(root.rglob("*"))
            if p.is_file()
        },
    )
    write_new(root / "release.json", release)
    return release


def verify_release(root: Path) -> Release:
    """Verify the complete portable artifact and each of its recorded files."""
    release = Release.model_validate_json((root / "release.json").read_bytes())
    for name, digest in release.files.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256_file(path) != digest:
            raise ValueError("RELEASE_FILE_CHANGED")
    return release


def main() -> None:
    """Finalize once from explicit review notes, or verify an existing release."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    args = parser.parse_args()
    if args.reviews:
        finalize(args.dataset, Reviews.model_validate_json(args.reviews.read_bytes()))
    release = verify_release(args.dataset)
    for case in release.cases:
        print(
            case.case_id,
            case.name,
            case.local_valid_fraction,
            case.context_valid_fraction,
            "missing:",
            case.context_missing_pixels,
            "modalities:",
            len(case.routed_modalities),
        )


if __name__ == "__main__":
    main()
