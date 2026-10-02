"""Content declarations for the existing Mercury development views, without values.

Apply only to the current catalogue/local-context-image/terrain-summary adapters.
These declarations describe model-visible representations, not new scientific data.
"""

from autonomous_modality.models import AssetContentInventory, InputDataModality

INVENTORY_VERSION = "mercury-development-contents-1.0"
SELECTOR_ALIGNMENT_VERSION = "selector-ap-input-supported-1.0"
SELECTOR_ALIGNMENT = (
    "Select for the question and answer requirements. A means distinct analytical tests "
    "feasible with the selected representations; later computation is allowed. P means "
    "plausible mechanisms or alternatives anchored in supplied features or representation "
    "limitations; classification labels alone do not contribute P. Compare feasible choices "
    "by their additional A and P contributions. After observation, distinguish new ideas "
    "from additional support for an existing direction. Use declared capabilities only; "
    "previews are not full numerical rasters. Proposals requiring extra scientific data "
    "do not count as current-input contributions. Preserve scientific validity and evidence "
    "fidelity. Keep A/P separate, without a fixed idea quota or an A+P objective."
)
ANSWER_POLICY_VERSION = "english-ap-input-supported-1.0"
ANSWER_POLICY = (
    "Assist an exploratory study of a Mercury crater. "
    "Write entirely in English, aiming for 200-300 words; no required number of ideas. "
    "Prioritize distinct analytical tests feasible with supplied representations and "
    "plausible explanations anchored in supplied features or representation limitations. "
    "Later computation is allowed; hypotheses need not be proven. For each idea, identify "
    "its evidence basis and main limitation. Merge overlapping ideas; omit routine steps "
    "and recaps, then end the answer immediately. "
    "Place ideas needing extra scientific data under 'Additional-data proposals', naming "
    "the missing inputs. Without case evidence, state the limitation and keep suggestions "
    "in that section. Distinguish proposed, observed and executed work; never invent results. "
    "Optical PNGs are stretched grayscale, not spectra. Terrain previews and sparse profiles "
    "are not a full numerical DEM; new full-grid analyses require that raster. Catalogue "
    "codes are provisional; absent ages, depths and population records remain unknown. "
    "Crop extrema are not rim/floor measurements. Check axes and locations; plot annotations "
    "are not terrain. Optical imagery and the DEM share MDIS ancestry. Preserve scientific "
    "validity and evidence fidelity."
)


def development_inventory(modality: InputDataModality) -> AssetContentInventory:
    """Return a fresh declaration for the existing core development representations."""
    common = {"version": INVENTORY_VERSION}
    if modality == InputDataModality.CRATER_CATALOG:
        return AssetContentInventory(
            **common,
            available_fields=[
                "id",
                "name",
                "lat_n",
                "lon_e_0",
                "diameter",
                "int_shp",
                "rim_shp",
                "cent_struc",
                "rayed",
            ],
            absent_fields=[
                "crater_depth",
                "absolute_age",
                "relative_age",
                "composition",
                "modification_history",
                "regional_crater_population",
            ],
            model_inputs=["One historical catalogue JSON record and morphology-code legend"],
            access_limits=[
                "Latitude/longitude in degrees; diameter in km.",
                "Field names are metadata; values become visible only after acquisition.",
                "Historical morphology codes require review; no measured depth or age is supplied.",
            ],
        )
    if modality == InputDataModality.OPTICAL_IMAGE:
        return AssetContentInventory(
            **common,
            available_fields=["optical_local", "optical_context"],
            absent_fields=["calibrated_reflectance", "composition", "absolute_age"],
            model_inputs=["Two display-stretched PNG views: local target and regional context"],
            access_limits=[
                "Images and coordinate annotations only; no executable raster-analysis tools.",
                "Brightness alone cannot establish composition or age.",
            ],
        )
    if modality == InputDataModality.TOPOGRAPHY:
        return AssetContentInventory(
            **common,
            available_fields=[
                "shape",
                "crs_wkt",
                "transform",
                "source_units",
                "source_scale",
                "source_offset",
                "valid_fraction",
                "minimum_m",
                "maximum_m",
                "mean_m",
                "std_m",
                "profiles.axis",
                "profiles.distance_km",
                "profiles.elevation_m",
            ],
            absent_fields=[
                "measured_crater_depth",
                "rim_floor_segmentation",
                "absolute_age",
                "computed_slope_map",
                "computed_registration_error",
            ],
            model_inputs=[
                "Elevation PNG and two fixed central profile PNGs (east-west, north-south)",
                "Whole-crop statistics and 17 index-spaced numeric samples per profile",
            ],
            access_limits=[
                "Elevation in metres, profile distance in km; crop range is not crater depth.",
                "Sparse samples may omit extrema; no direct model access to full TIFF/CSV arrays.",
                "New gradients, segmentation and registration measurements require external tools.",
                "The DEM and optical images share MDIS ancestry.",
            ],
        )
    raise ValueError("No development-view inventory is defined for this modality")
