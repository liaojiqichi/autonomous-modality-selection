"""Versioned declarations for the four compact Mercury evidence packages.

These describe representations, not target-specific observations. Frozen inventories
and historical manifests remain unchanged; callers explicitly adopt this version.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from pydantic import Field

from autonomous_modality.development_inputs import development_inventory
from autonomous_modality.models import AssetContentInventory, InputDataModality, StrictModel

ASSET_DESCRIPTION_VERSION = "mercury-four-modality-descriptions-2.0"


class ModalityDescription(StrictModel):
    """The same four sections for each scientific modality."""

    contents: str = Field(min_length=1)
    coverage: str = Field(min_length=1)
    supported_analyses: str = Field(min_length=1)
    interpretation_limits: str = Field(min_length=1)

    def text(self) -> str:
        """Render a stable declaration for existing notebook interfaces."""
        return " ".join(
            f"{label}: {getattr(self, field)}"
            for label, field in (
                ("Contents", "contents"),
                ("Coverage", "coverage"),
                ("Supported analyses", "supported_analyses"),
                ("Interpretation limits", "interpretation_limits"),
            )
        )


_DESCRIPTIONS = {
    "CRATER_CATALOG": ModalityDescription(
        contents="One historical crater record with identifier, name, coordinates, diameter, "
        "interior morphology, rim morphology, central-structure classification and ray "
        "classification, accompanied by morphology-code definitions.",
        coverage="Target-level attributes and classifications; coordinates in degrees and "
        "diameter in kilometres.",
        supported_analyses="Identify a specific classification claim to check; compare it "
        "with features in other supplied modalities; use the recorded centre and diameter "
        "as spatial references.",
        interpretation_limits="Classifications reflect earlier image interpretation. "
        "Measured depth, age, composition and modification history are absent. "
        "Population-level comparisons require multiple records.",
    ),
    "OPTICAL_IMAGE": ModalityDescription(
        contents="Two display-stretched grayscale images with coordinate annotations.",
        coverage="A local view of the crater and a context view of surrounding terrain.",
        supported_analyses="Inspect visible rim, wall, floor and central structures to "
        "assess morphology classifications; compare local and background textures; examine "
        "visible overlap, truncation or continuity when considering modification and "
        "preserved structure, where these features can be resolved.",
        interpretation_limits="Recognition depends on resolution, illumination and contrast. "
        "Brightness alone cannot establish height, composition or age. Quantitative pixel "
        "analysis requires the underlying raster. Optical imagery and the DEM share MDIS ancestry.",
    ),
    "TOPOGRAPHY": ModalityDescription(
        contents="An elevation map, central east-west and south-north profile plots, "
        "whole-crop elevation statistics, and 17 index-spaced distance-elevation samples "
        "per profile. Elevation is in metres and distance in kilometres.",
        coverage="The local crop and two perpendicular transects through the catalogue centre.",
        supported_analyses="Compare elevations and approximate gradients at matched profile "
        "distances, accounting for sample spacing; assess whether relief differences occur "
        "near the centre or extend towards crop edges; compare relief with catalogue "
        "classifications and other supplied surface evidence.",
        interpretation_limits="Fixed profiles may miss off-axis features and local extrema. "
        "Crop statistics describe the whole crop. Crater depth requires a reference surface "
        "and measurement locations; full-grid slopes and new regional statistics require "
        "the raster. Map colours encode elevation. "
        "The DEM and optical imagery share MDIS ancestry.",
    ),
    "MULTISPECTRAL_IMAGE": ModalityDescription(
        contents="Regional mean reflectance (I/F), spatial standard deviation and valid-pixel "
        "count for eight MDIS bands at 430, 480, 560, 630, 750, 830, 900 and 1000 nm, as text.",
        coverage="Four geometric regions, with r the distance from the catalogue centre "
        "and D the catalogue diameter: inner disk (0 <= r < 0.25D), middle annulus "
        "(0.25D <= r < 0.5D), outer annulus (0.5D <= r < D), and background annulus "
        "(D <= r < 2D).",
        supported_analyses="Compare regional reflectance at specified wavelengths; calculate "
        "band ratios or broad spectral slopes from regional means; compare regional "
        "contrasts with within-region variation when considering material differences "
        "and spatial mixing.",
        interpretation_limits="Regions can contain several geological units. Spatial standard "
        "deviation is not measurement uncertainty. Regional summaries cannot locate individual "
        "spectral features or identify a unique composition. Illumination and landform checks "
        "require suitable complementary evidence. MDIS spectral and grayscale products share "
        "instrument ancestry.",
    ),
}


def modality_description(modality: InputDataModality | str) -> ModalityDescription:
    """Return a fresh declaration; reject unsupported modalities."""
    name = InputDataModality(modality).value
    if name not in _DESCRIPTIONS:
        raise ValueError(f"No compact four-modality description: {name}")
    return _DESCRIPTIONS[name].model_copy(deep=True)


def modality_inventory(modality: InputDataModality | str) -> AssetContentInventory:
    """Describe actual compact inputs, including four regions and eight bands."""
    modality = InputDataModality(modality)
    declaration = modality_description(modality)
    if modality == InputDataModality.MULTISPECTRAL_IMAGE:
        inventory = AssetContentInventory(
            version=ASSET_DESCRIPTION_VERSION,
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
                "pixelwise_spectral_locations",
            ],
            model_inputs=[declaration.contents, declaration.coverage],
            access_limits=[declaration.interpretation_limits],
        )
    else:
        inventory = development_inventory(modality).model_copy(deep=True)
        inventory.version = ASSET_DESCRIPTION_VERSION
        inventory.model_inputs = [declaration.contents, declaration.coverage]
        inventory.access_limits = [declaration.interpretation_limits]
    return inventory


def describe_assets(assets: Mapping[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Copy notebook assets and replace only their descriptions and inventories.

    Supports subsets of the four declared modalities. Costs, evidence paths and
    other caller metadata are preserved. No evidence or scientific values are read.
    """
    if not assets:
        raise ValueError("At least one modality is required")
    result = copy.deepcopy(dict(assets))
    for name, asset in result.items():
        asset["description"] = modality_description(name).text()
        asset["content_inventory"] = modality_inventory(name).model_dump(mode="json")
    return result
