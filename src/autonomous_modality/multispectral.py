"""Offline multispectral region summaries and verified model-evidence routing.

This adapter consumes locally prepared radiance-factor arrays, not RGB previews.
Calibration and georeferencing must be verified during product preparation.
"""

from __future__ import annotations

import hashlib
from itertools import pairwise
from pathlib import Path
from typing import Literal, Self

import numpy as np
from pydantic import Field, model_validator

from autonomous_modality.iterative import ContentBlock, EvidenceObservation, LoadEvidence
from autonomous_modality.models import (
    INPUT_MODALITY_TAXONOMY_VERSION,
    AssetAvailability,
    AssetContentInventory,
    DataAssetProfile,
    InputDataModality,
    NonEmptyString,
    StrictModel,
)

VERSION = "multispectral-regions-1.0"
LIMITATIONS = [
    "Numeric summaries of declared regions; no full spectral raster is exposed to the model.",
    "Band differences alone do not identify minerals, composition, age or volcanism.",
    "Illumination, photometric correction, resolution and registration can affect differences.",
    "Region labels describe supplied masks, not confirmed geological interpretations.",
    "MDIS multispectral and MDIS grayscale imagery share instrument ancestry.",
]


class SpectralBand(StrictModel):
    band_id: NonEmptyString
    wavelength_nm: float = Field(gt=0)


class SpectralMetadata(StrictModel):
    case_id: NonEmptyString
    product_id: NonEmptyString
    source_uri: NonEmptyString
    instrument: Literal["MESSENGER_MDIS_WAC"]
    quantity: Literal["radiance_factor_I_over_F"]
    processing: Literal["calibrated_photometrically_corrected"]
    calibration_reference: NonEmptyString
    spatial_reference: NonEmptyString
    pixel_resolution_m: float = Field(gt=0)
    coverage_description: NonEmptyString
    registration_limitations: NonEmptyString
    provenance_kind: Literal["observed", "synthetic_fixture"]
    bands: list[SpectralBand] = Field(min_length=3, max_length=16)

    @model_validator(mode="after")
    def unique_bands(self) -> Self:
        """Require unique bands and strictly increasing wavelengths."""
        wavelengths = [b.wavelength_nm for b in self.bands]
        if len({b.band_id for b in self.bands}) != len(self.bands):
            raise ValueError("DUPLICATE_BAND_ID")
        if any(a >= b for a, b in pairwise(wavelengths)):
            raise ValueError("WAVELENGTHS_MUST_INCREASE")
        return self


class BandStatistics(StrictModel):
    band_id: NonEmptyString
    count: int = Field(ge=0, strict=True)
    mean: float | None
    std: float | None = Field(ge=0)

    @model_validator(mode="after")
    def missing_values(self) -> Self:
        """Missing observations must remain explicit, never fabricated zeros."""
        if (self.count == 0) != (self.mean is None and self.std is None):
            raise ValueError("INCONSISTENT_MISSING_STATISTICS")
        if self.count > 0 and (self.mean is None or self.std is None):
            raise ValueError("MISSING_STATISTIC")
        return self


class SpectralRegion(StrictModel):
    region_id: NonEmptyString
    mask_pixels: int = Field(gt=0, strict=True)
    statistics: list[BandStatistics] = Field(min_length=3, max_length=16)


class MultispectralPackage(StrictModel):
    version: Literal["multispectral-regions-1.0"] = VERSION
    taxonomy_version: Literal["scientific-input-modalities-1.1"] = INPUT_MODALITY_TAXONOMY_VERSION
    modality: Literal[InputDataModality.MULTISPECTRAL_IMAGE] = InputDataModality.MULTISPECTRAL_IMAGE
    metadata: SpectralMetadata
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    regions: list[SpectralRegion] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def aligned_regions(self) -> Self:
        """Require a complete, aligned band inventory for every declared region."""
        ids = [r.region_id for r in self.regions]
        if len(set(ids)) != len(ids):
            raise ValueError("DUPLICATE_REGION_ID")
        expected = [b.band_id for b in self.metadata.bands]
        for region in self.regions:
            if [s.band_id for s in region.statistics] != expected:
                raise ValueError("REGION_BAND_MISMATCH")
            if any(s.count > region.mask_pixels for s in region.statistics):
                raise ValueError("INVALID_REGION_COUNT")
        if not any(s.count for r in self.regions for s in r.statistics):
            raise ValueError("NO_VALID_SPECTRAL_VALUES")
        return self


def summarize_multispectral(source: Path, metadata: SpectralMetadata) -> MultispectralPackage:
    """Read a local NPZ: float reflectance[B,H,W], bool roi_<id>[H,W].

    Nodata must have been converted to NaN; nonfinite samples are excluded.
    No downloading, calibration inference, segmentation or LLM execution occurs.
    """
    metadata = SpectralMetadata.model_validate_json(metadata.model_dump_json())
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with np.load(source, allow_pickle=False) as data:
        values = data["reflectance"]
        if values.dtype.kind != "f" or values.ndim != 3 or values.shape[0] != len(metadata.bands):
            raise ValueError("EXPECTED_FLOAT_BAND_Y_X_ARRAY")
        names = sorted(name for name in data.files if name.startswith("roi_"))
        if not 1 <= len(names) <= 8:
            raise ValueError("EXPECTED_ONE_TO_EIGHT_REGIONS")
        regions = []
        for name in names:
            mask = data[name]
            if mask.dtype.kind != "b" or mask.shape != values.shape[1:] or not mask.any():
                raise ValueError("INVALID_REGION_MASK")
            statistics = []
            for band, array in zip(metadata.bands, values, strict=True):
                samples = array[mask & np.isfinite(array)].astype(np.float64)
                statistics.append(
                    BandStatistics(
                        band_id=band.band_id,
                        count=int(samples.size),
                        mean=float(samples.mean()) if samples.size else None,
                        std=float(samples.std(ddof=0)) if samples.size else None,
                    )
                )
            regions.append(
                SpectralRegion(
                    region_id=name[4:], mask_pixels=int(mask.sum()), statistics=statistics
                )
            )
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError("SOURCE_CHANGED_DURING_SUMMARY")
    return MultispectralPackage(metadata=metadata, source_sha256=before, regions=regions)


def multispectral_asset(
    package: MultispectralPackage, *, estimated_cost: float
) -> DataAssetProfile:
    """Create an inventory without exposing region values before acquisition.

    The caller must explicitly set and document ordinal or measured-token cost.
    Synthetic fixtures are never available scientific assets.
    """
    package = MultispectralPackage.model_validate_json(package.model_dump_json())
    return DataAssetProfile(
        asset_id=f"multispectral-{package.metadata.case_id}-{package.metadata.product_id}",
        modality=InputDataModality.MULTISPECTRAL_IMAGE,
        title="Calibrated MDIS multispectral regional summaries",
        availability=AssetAvailability.AVAILABLE
        if package.metadata.provenance_kind == "observed"
        else AssetAvailability.UNAVAILABLE,
        source_uri=package.metadata.source_uri,
        data_format="multispectral-regions-1.0 JSON",
        spatial_resolution_m=package.metadata.pixel_resolution_m,
        estimated_cost=estimated_cost,
        limitations=LIMITATIONS,
        analytical_capabilities=[
            "Compare regional band responses with sampling and calibration caveats"
        ],
        explanatory_capabilities=[
            "Test surface spectral contrasts against illumination alternatives"
        ],
        model_representations=["Wavelength metadata and per-region numeric band statistics"],
        content_inventory=AssetContentInventory(
            version=VERSION,
            available_fields=[
                "bands.wavelength_nm",
                "regions.statistics.mean",
                "regions.statistics.std",
                "regions.statistics.count",
                "calibration_reference",
                "spatial_reference",
            ],
            absent_fields=[
                "mineral_identification",
                "absolute_age",
                "confirmed_volcanism",
                "full_numeric_spectral_cube",
            ],
            model_inputs=["Bounded JSON: at most 8 regions and 16 spectral bands"],
            access_limits=LIMITATIONS,
        ),
    )


def multispectral_loader(
    package_path: Path, *, expected_case_id: str, source_path: Path
) -> LoadEvidence:
    """Pin a prepared package and numeric source; verify both on every acquisition."""
    raw = package_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    package = MultispectralPackage.model_validate_json(raw)
    if package.metadata.case_id != expected_case_id:
        raise ValueError("MULTISPECTRAL_CASE_MISMATCH")
    if package.metadata.provenance_kind != "observed":
        raise ValueError("SYNTHETIC_PACKAGE_NOT_SCIENTIFIC_EVIDENCE")

    def load(modality: InputDataModality) -> EvidenceObservation:
        if modality != InputDataModality.MULTISPECTRAL_IMAGE:
            raise ValueError("WRONG_MULTISPECTRAL_MODALITY")
        if hashlib.sha256(package_path.read_bytes()).hexdigest() != digest:
            raise ValueError("MULTISPECTRAL_PACKAGE_CHANGED")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != package.source_sha256:
            raise ValueError("MULTISPECTRAL_SOURCE_CHANGED")
        return EvidenceObservation(
            modality=modality,
            package_sha256=digest,
            evidence_sha256={"summary": digest, "numeric_source": package.source_sha256},
            blocks=[
                ContentBlock(
                    type="text",
                    text="MULTISPECTRAL_IMAGE evidence. "
                    + " ".join(LIMITATIONS)
                    + "\n"
                    + package.model_dump_json(),
                )
            ],
        )

    return load


def main() -> None:
    """Prepare a local package, refusing to overwrite an existing output."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    metadata = SpectralMetadata.model_validate_json(args.metadata.read_bytes())
    package = summarize_multispectral(args.source, metadata)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(package.model_dump_json(indent=2))
    print(f"Prepared {package.metadata.provenance_kind} package: {args.output}")


if __name__ == "__main__":
    main()
