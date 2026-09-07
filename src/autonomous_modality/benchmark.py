"""Offline case QA and portable evidence packages; no inference or expert certification."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

import numpy as np
import rasterio
from matplotlib.image import imread
from pydantic import Field, model_validator
from rasterio.crs import CRS

from autonomous_modality.acquisition import DownloadRecord, load_sources, sha256_file
from autonomous_modality.models import (
    BaselineSelectionResult,
    CraterQuestion,
    CraterQuestionType,
    CraterReference,
    DataAssetProfile,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
    NonEmptyString,
    StrictModel,
)
from autonomous_modality.pilot import RADIUS_M, CatalogueRow, PilotCase, PilotRun
from autonomous_modality.selection import select_baseline

VERSION = "mercury-benchmark-1.1"
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
M = InputDataModality
FILES = {
    "catalogue.json": (M.CRATER_CATALOG, "catalogue_record"),
    "image_local.tif": (M.OPTICAL_IMAGE, "numeric_raster"),
    "image_context.tif": (M.OPTICAL_IMAGE, "numeric_raster"),
    "image_local.png": (M.OPTICAL_IMAGE, "image_preview"),
    "image_context.png": (M.OPTICAL_IMAGE, "image_preview"),
    "dem_local.tif": (M.TOPOGRAPHY, "numeric_raster"),
    "dem_local.png": (M.TOPOGRAPHY, "elevation_preview"),
    "east_west_profile.csv": (M.TOPOGRAPHY, "numeric_profile"),
}
LIMITS = [
    "Provisional exploratory use only; no expert certification or measured registration error.",
    "Historical 2011 catalogue coordinates and morphology codes are not modern ground truth.",
    "Image DN is display-stretched, not calibrated reflectance or mineral composition.",
    "DEM and optical imagery share MDIS ancestry and are not independent observations.",
    "Pixel spacing is not effective feature resolution or vertical accuracy.",
    "The central E-W profile is not a measured crater depth; no rim/floor segmentation exists.",
    "No absolute ages, unique formation mechanism, or impact parameters can be established here.",
]


class VisualReview(StrictModel):
    """Assistant visual screening, explicitly separate from expert adjudication."""

    case_id: int = Field(gt=0)
    status: Literal["provisional_pass", "hold"]
    observation: NonEmptyString
    concern: NonEmptyString
    reviewer: Literal["Codex visual screening; not a planetary-science expert"]
    evidence_files: list[NonEmptyString] = Field(min_length=2)


class ReviewSet(StrictModel):
    """Pinned visual decisions for one immutable source run."""

    version: Literal["visual-review-1.0"] = "visual-review-1.0"
    source_run_sha256: Sha256
    reviewed_utc: datetime
    reviews: list[VisualReview] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        """Prevent silently replacing duplicate reviews."""
        if len({item.case_id for item in self.reviews}) != len(self.reviews):
            raise ValueError("duplicate visual reviews")
        return self


class QuestionSpec(StrictModel):
    """Frozen scientific question, not a target answer or modality-selection oracle."""

    question_id: Annotated[str, Field(pattern=r"^Q[1-9][0-9]*$")]
    question_type: CraterQuestionType
    text: NonEmptyString
    answer_requirements: list[NonEmptyString] = Field(min_length=1)
    quantitative_modalities: set[InputDataModality] = Field(default_factory=set)
    quantitative_prerequisites: list[NonEmptyString] = Field(default_factory=list)


class QuestionSet(StrictModel):
    """Three to five reusable questions fixed before answer-generation experiments."""

    version: Literal["mercury-questions-1.0", "mercury-questions-2.0"] = "mercury-questions-1.0"
    questions: list[QuestionSpec] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def unique_questions(self) -> Self:
        """Reject ambiguous question identifiers."""
        if len({q.question_id for q in self.questions}) != len(self.questions):
            raise ValueError("duplicate question IDs")
        return self


class EvidenceFile(StrictModel):
    """Actual bytes and scientific modality, independent of representation type."""

    path: NonEmptyString
    modality: InputDataModality
    representation: Literal[
        "catalogue_record",
        "numeric_raster",
        "image_preview",
        "elevation_preview",
        "numeric_profile",
    ]
    sha256: Sha256
    bytes: int = Field(gt=0)
    units: NonEmptyString
    source_id: NonEmptyString
    parent_paths: list[str] = Field(default_factory=list)


class CaseAudit(StrictModel):
    """Technical checks cannot upgrade a held visual review."""

    case_id: int
    name: str
    visual: VisualReview
    technical_errors: list[str]
    minimum_valid_fraction: float = Field(ge=0, le=1)
    evidence_hashes: dict[str, Sha256]
    source_hashes: dict[str, Sha256]
    status: Literal["provisional_pass", "hold", "reject"]

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        """Pass only when technical and visual gates agree."""
        expected = "reject" if self.technical_errors else self.visual.status
        if self.case_id != self.visual.case_id or self.status != expected:
            raise ValueError("inconsistent audit status or case ID")
        return self


class InputPackage(StrictModel):
    """Portable available-evidence pool; audit notes are not selector inputs."""

    schema_version: Literal["input-package-1.0"] = "input-package-1.0"
    case: CatalogueRow
    qa_status: Literal["provisional_pass"] = "provisional_pass"
    expert_approved: Literal[False] = False
    assets: list[DataAssetProfile]
    files: list[EvidenceFile] = Field(min_length=1)
    source_hashes: dict[str, Sha256]
    limitations: list[str]
    cost_definition: str = "Ordinal units, not tokens: catalogue=1, image=2, topography=2."
    llm_called: Literal[False] = False

    @model_validator(mode="after")
    def validate_file_mapping(self) -> Self:
        """Every representation must belong to exactly one declared modality."""
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError("duplicate evidence paths")
        modalities = {a.modality for a in self.assets}
        if len(modalities) != len(self.assets) or len({a.asset_id for a in self.assets}) != len(
            self.assets
        ):
            raise ValueError("duplicate package assets")
        if {f.modality for f in self.files} != modalities:
            raise ValueError("evidence and asset modalities differ")
        for asset in self.assets:
            if asset.source_uri not in {f.path for f in self.files if f.modality == asset.modality}:
                raise ValueError("asset source must reference its own evidence")
        paths = {file.path: file.modality for file in self.files}
        for file in self.files:
            if file.source_id not in self.source_hashes:
                raise ValueError("untracked evidence source")
            if any(
                parent == file.path or paths.get(parent) != file.modality
                for parent in file.parent_paths
            ):
                raise ValueError("invalid or cross-modal evidence parent")
        return self


def local_file(root: Path, relative: str) -> Path:
    """Resolve portable package references without traversal or escaped symlinks."""
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative or ":" in relative:
        raise ValueError("unsafe relative evidence path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"missing or escaped evidence: {relative}")
    return path


def audit_case(
    case: PilotCase, root: Path, review: VisualReview, sources: list[DownloadRecord]
) -> CaseAudit:
    """Check immutable bytes, grids, coverage, numeric profiles and reviewed displays."""
    errors: list[str] = []
    fractions: list[float] = []
    hashes: dict[str, str] = {}
    source_hashes = {source.source.source_id: source.sha256 for source in sources}
    directory = root / f"crater-{case.catalogue.id}"
    try:
        expected_products = {"image_local.tif", "image_context.tif", "dem_local.tif"}
        if (
            len(case.products) != 3
            or {Path(p.data_path).name for p in case.products} != expected_products
        ):
            raise ValueError("expected exactly three named raster products")
        for name in (*FILES, "overview.png", "case.json"):
            path = local_file(directory, name)
            hashes[name] = sha256_file(path)
            if name.endswith(".png"):
                display = imread(path)
                if display.size == 0 or not np.isfinite(display).all():
                    raise ValueError("invalid preview")
        if not {"overview.png", "dem_local.png"}.issubset(review.evidence_files):
            raise ValueError("visual review must cover overview and DEM")
        for name in review.evidence_files:
            local_file(directory, name)
        if PilotCase.model_validate_json(local_file(directory, "case.json").read_text()) != case:
            raise ValueError("case record differs from source run")
        if (
            CatalogueRow.model_validate_json(local_file(directory, "catalogue.json").read_text())
            != case.catalogue
        ):
            raise ValueError("catalogue differs from case")
        crs = CRS.from_string(
            f"+proj=aeqd +lat_0={case.catalogue.lat_n} +lon_0={case.catalogue.lon_e_0} "
            f"+R={RADIUS_M} +units=m +no_defs"
        )
        for product in case.products:
            name = Path(product.data_path).name
            if hashes[name] != product.data_sha256:
                raise ValueError(f"changed raster: {name}")
            if source_hashes.get(product.source_id) != product.source_sha256:
                raise ValueError(f"unverified source lineage: {name}")
            with rasterio.open(local_file(directory, name)) as dataset:
                if (
                    dataset.count != 1
                    or dataset.crs != crs
                    or dataset.crs != CRS.from_wkt(product.derived_crs_wkt)
                ):
                    raise ValueError(f"CRS/band mismatch: {name}")
                if dataset.width != dataset.height or dataset.width != product.width_pixels:
                    raise ValueError(f"shape mismatch: {name}")
                resolution = product.resolution_m
                half = dataset.width * resolution / 2
                expected = rasterio.transform.from_origin(-half, half, resolution, resolution)
                if (
                    not dataset.transform.almost_equals(expected)
                    or dataset.scales != (1.0,)
                    or dataset.offsets != (0.0,)
                ):
                    raise ValueError(f"grid or unprocessed scale: {name}")
                width = 5 if name == "image_context.tif" else 2
                if dataset.width != math.ceil(case.catalogue.diameter * 1000 * width / resolution):
                    raise ValueError(f"crop extent mismatch: {name}")
                array = dataset.read(1, masked=True).astype("float32").filled(np.nan)
                fraction = float(np.isfinite(array).mean())
                fractions.append(fraction)
                if fraction < 0.95 or not math.isclose(
                    fraction, product.valid_fraction, abs_tol=1e-9
                ):
                    raise ValueError(f"coverage failure: {name}")
                if np.nanmax(array) <= np.nanmin(array):
                    raise ValueError(f"constant raster: {name}")
                if name == "dem_local.tif":
                    with local_file(directory, "east_west_profile.csv").open(newline="") as stream:
                        reader = csv.DictReader(stream)
                        if reader.fieldnames != ["east_from_catalogue_centre_km", "elevation_m"]:
                            raise ValueError("invalid profile columns")
                        rows = list(reader)
                    n = array.shape[0]
                    profile = array[n // 2] if n % 2 else (array[n // 2 - 1] + array[n // 2]) / 2
                    actual = np.array(
                        [float(r["elevation_m"]) if r["elevation_m"] else np.nan for r in rows]
                    )
                    x = np.array([float(r["east_from_catalogue_centre_km"]) for r in rows])
                    expected_x = (np.arange(n) + 0.5 - n / 2) * resolution / 1000
                    if (
                        actual.shape != profile.shape
                        or not np.allclose(actual, profile, equal_nan=True)
                        or not np.allclose(x, expected_x)
                    ):
                        raise ValueError("profile differs from numeric DEM")
    except (ValueError, OSError, rasterio.errors.RasterioError) as exc:
        errors.append(str(exc))
    return CaseAudit(
        case_id=case.catalogue.id,
        name=case.catalogue.name,
        visual=review,
        technical_errors=errors,
        minimum_valid_fraction=min(fractions, default=0),
        evidence_hashes=hashes,
        source_hashes=source_hashes,
        status="reject" if errors else review.status,
    )


def save_model(path: Path, model: StrictModel) -> None:
    """Persist strictly modelled, create-only output."""
    with path.open("x", encoding="utf-8") as stream:
        stream.write(model.model_dump_json(indent=2))


def build_package(
    case: PilotCase, audit: CaseAudit, source_root: Path, destination: Path
) -> InputPackage:
    """Copy verified evidence once; never include multimodal overview as model evidence."""
    if audit.status != "provisional_pass" or audit.case_id != case.catalogue.id:
        raise ValueError("only matching provisionally approved cases may be packaged")
    if "raw" in [part.lower() for part in destination.resolve().parts]:
        raise ValueError("package must be outside raw directories")
    directory = source_root / f"crater-{case.catalogue.id}"
    paths = {name: local_file(directory, name) for name in FILES}
    for name, path in paths.items():
        if sha256_file(path) != audit.evidence_hashes.get(name):
            raise ValueError("evidence changed after audit")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "evidence").mkdir()
    files = []
    for name, (modality, representation) in FILES.items():
        path = destination / "evidence" / name
        shutil.copyfile(paths[name], path)
        if sha256_file(path) != audit.evidence_hashes[name]:
            raise ValueError("copy checksum mismatch")
        files.append(
            EvidenceFile(
                path=f"evidence/{name}",
                modality=modality,
                representation=representation,
                sha256=audit.evidence_hashes[name],
                bytes=path.stat().st_size,
                units=(
                    "latitude/longitude: degrees; diameter: km; morphology: historical codes"
                    if modality == M.CRATER_CATALOG
                    else "display-stretched DN, not reflectance"
                    if modality == M.OPTICAL_IMAGE
                    else "elevation: metres relative to 2439.4 km radius; profile distance: km"
                ),
                source_id=(
                    "herrick-2011-catalog"
                    if modality == M.CRATER_CATALOG
                    else "mdis-loi-v1"
                    if modality == M.OPTICAL_IMAGE
                    else "usgs-dem-v2"
                ),
                parent_paths=(
                    [f"evidence/{Path(name).with_suffix('.tif').name}"]
                    if name.endswith(".png")
                    else ["evidence/dem_local.tif"]
                    if name.endswith(".csv")
                    else []
                ),
            )
        )
    assets = []
    for asset in case.assets:
        representations = [f for f in files if f.modality == asset.modality]
        payload = asset.model_dump()
        payload.update(
            source_uri=representations[0].path,
            model_representations=list(dict.fromkeys(f.representation for f in representations)),
            quality_score=None,
            limitations=[*asset.limitations, *LIMITS],
        )
        assets.append(DataAssetProfile.model_validate(payload))
    package = InputPackage(
        case=case.catalogue,
        assets=assets,
        files=files,
        source_hashes=audit.source_hashes,
        limitations=LIMITS,
    )
    save_model(destination / "package.json", package)
    return package


def selected_evidence(package: InputPackage, result: BaselineSelectionResult) -> list[EvidenceFile]:
    """Route only selected modalities; never leak other modalities through overview panels."""
    declared = {asset.asset_id: asset.modality for asset in package.assets}
    for item in result.decision.selected:
        if declared.get(item.asset_id) != item.modality:
            raise ValueError("selection does not belong to this package")
    modalities = {item.modality for item in result.decision.selected}
    return [file for file in package.files if file.modality in modalities]


def verify_package(root: Path) -> InputPackage:
    """Validate a relocated package and every evidence file before it is consumed."""
    package = InputPackage.model_validate_json((root / "package.json").read_text(encoding="utf-8"))
    for file in package.files:
        path = local_file(root, file.path)
        if path.stat().st_size != file.bytes or sha256_file(path) != file.sha256:
            raise ValueError(f"package evidence checksum mismatch: {file.path}")
    return package


class PreparedTask(StrictModel):
    """Recorded selector input and routed evidence; no answer generation implied."""

    schema_version: Literal["prepared-task-1.0", "prepared-task-1.1"] = "prepared-task-1.1"
    question_version: str
    request: InputSelectionRequest
    result: BaselineSelectionResult
    selected_files: list[EvidenceFile]
    answer_requirements: list[str]
    condition: Literal["budget-selection", "fixed-image-topography"] = "budget-selection"
    missing_quantitative_modalities: set[InputDataModality] = Field(default_factory=set)
    unverified_quantitative_prerequisites: list[str] = Field(default_factory=list)
    quantitative_status: Literal["not_assessed", "not_ready"] = "not_assessed"
    llm_called: Literal[False] = False

    @model_validator(mode="after")
    def validate_control(self) -> Self:
        """Fixed controls must retain exactly the requested modalities and evidence."""
        modalities = {item.modality for item in self.result.decision.selected}
        if {file.modality for file in self.selected_files} != modalities:
            raise ValueError("selected evidence modalities differ from selection")
        if self.condition == "fixed-image-topography":
            expected = {M.OPTICAL_IMAGE, M.TOPOGRAPHY}
            if modalities != expected or self.request.constraints.required_modalities != expected:
                raise ValueError("fixed control requires image and topography only")
            if (
                self.request.constraints.maximum_modalities != 2
                or self.request.constraints.maximum_total_cost != 4
            ):
                raise ValueError("fixed control requires two modalities and budget 4")
        blocked = bool(
            self.missing_quantitative_modalities or self.unverified_quantitative_prerequisites
        )
        if (self.quantitative_status == "not_ready") != blocked:
            raise ValueError("inconsistent quantitative readiness")
        return self


def prepare_task(
    package: InputPackage,
    question: QuestionSpec,
    budget: int,
    *,
    fixed_image_topography: bool = False,
    question_version: str = "mercury-questions-1.0",
) -> PreparedTask:
    """Use the same frozen question and metadata under each budget condition."""
    row = package.case
    if fixed_image_topography and budget != 4:
        raise ValueError("fixed image-topography control requires budget 4")
    constraints = InputSelectionConstraints(maximum_modalities=3, maximum_total_cost=budget)
    if fixed_image_topography:
        constraints = InputSelectionConstraints(
            maximum_modalities=2,
            maximum_total_cost=4,
            required_modalities={M.OPTICAL_IMAGE, M.TOPOGRAPHY},
            forbidden_modalities=set(M) - {M.OPTICAL_IMAGE, M.TOPOGRAPHY},
        )
    request = InputSelectionRequest(
        question=CraterQuestion(
            question_id=f"{row.id}-{question.question_id}",
            text=question.text.replace("{crater}", row.name),
            question_type=question.question_type,
            crater=CraterReference(
                crater_id=str(row.id),
                name=row.name,
                latitude=row.lat_n,
                longitude=row.lon_e_0,
                # Coordinates identify the target; diameter remains selectable catalogue evidence.
                diameter_km=None,
            ),
        ),
        assets=package.assets,
        constraints=constraints,
    )
    result = select_baseline(request)
    return PreparedTask(
        question_version=question_version,
        request=request,
        result=result,
        selected_files=selected_evidence(package, result),
        answer_requirements=question.answer_requirements,
        condition="fixed-image-topography" if fixed_image_topography else "budget-selection",
        missing_quantitative_modalities=question.quantitative_modalities
        - {item.modality for item in result.decision.selected},
        unverified_quantitative_prerequisites=question.quantitative_prerequisites,
        quantitative_status="not_ready"
        if question.quantitative_prerequisites
        or question.quantitative_modalities - {item.modality for item in result.decision.selected}
        else "not_assessed",
    )


class BenchmarkRun(StrictModel):
    """Complete screening ledger including excluded targets to expose selection bias."""

    version: Literal["mercury-benchmark-1.0", "mercury-benchmark-1.1"] = VERSION
    created_utc: datetime
    source_run_sha256: Sha256
    review_sha256: Sha256
    questions_sha256: Sha256
    code_sha256: dict[str, Sha256]
    sources: list[DownloadRecord]
    source_archive_included: Literal[False] = False
    audits: list[CaseAudit]
    packages: list[str]
    prepared_tasks: int
    limitations: list[str]
    llm_called: Literal[False] = False


def main() -> None:
    """Verify local sources, audit all cases and create a new portable benchmark folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists() or "raw" in [part.lower() for part in root.parts]:
        raise ValueError("output must be a new directory outside raw")
    run = PilotRun.model_validate_json(args.run.read_text(encoding="utf-8"))
    reviews = ReviewSet.model_validate_json(args.reviews.read_text(encoding="utf-8"))
    questions = QuestionSet.model_validate_json(args.questions.read_text(encoding="utf-8"))
    if sha256_file(args.run) != reviews.source_run_sha256:
        raise ValueError("review is not pinned to this run")
    by_id = {review.case_id: review for review in reviews.reviews}
    ids = [case.catalogue.id for case in run.cases]
    if len(set(ids)) != len(ids) or set(by_id) != set(ids):
        raise ValueError("visual reviews must cover every case exactly once")
    sources = load_sources(args.sources)
    audits = [
        audit_case(case, args.run.parent, by_id[case.catalogue.id], sources) for case in run.cases
    ]
    root.mkdir(parents=True)
    save_model(root / "questions.json", questions)
    save_model(root / "visual_reviews.json", reviews)
    packages = []
    tasks = 0
    for case, audit in zip(run.cases, audits, strict=True):
        print(f"{case.catalogue.name}: {audit.status}; {audit.technical_errors}", flush=True)
        if audit.status != "provisional_pass":
            continue
        relative = f"crater-{case.catalogue.id}"
        package = build_package(case, audit, args.run.parent, root / relative)
        packages.append(f"{relative}/package.json")
        for question in questions.questions:
            for budget in (3, 5, 4):
                task = prepare_task(
                    package,
                    question,
                    budget,
                    fixed_image_topography=budget == 4,
                    question_version=questions.version,
                )
                label = "fixed-image-topography" if budget == 4 else f"budget-{budget}"
                save_model(root / relative / f"{question.question_id}-{label}.json", task)
                tasks += 1
    ledger = BenchmarkRun(
        created_utc=datetime.now(UTC),
        source_run_sha256=sha256_file(args.run),
        review_sha256=sha256_file(args.reviews),
        questions_sha256=sha256_file(args.questions),
        code_sha256={p.name: sha256_file(p) for p in Path(__file__).parent.glob("*.py")},
        sources=sources,
        audits=audits,
        packages=packages,
        prepared_tasks=tasks,
        limitations=[
            *LIMITS,
            "Convenience development set, not an unbiased held-out test set.",
            "Visual reviewers saw all candidates. Selection bias must be reported.",
            "Source receipts describe external archives; only derived evidence is bundled.",
        ],
    )
    save_model(root / "audit.json", ledger)
    print(json.dumps({"packages": len(packages), "prepared_tasks": tasks, "output": str(root)}))


if __name__ == "__main__":
    main()
