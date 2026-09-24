"""Content declarations for the existing Mercury development views, without values.

Apply only to the current catalogue/local-context-image/terrain-summary adapters.
These declarations describe model-visible representations, not new scientific data.
"""

from autonomous_modality.models import AssetContentInventory, InputDataModality

INVENTORY_VERSION = "mercury-development-contents-1.0"
ANSWER_POLICY_VERSION = "english-ap-concise-1.0"
ANSWER_POLICY = (
    "Assist an exploratory study of a Mercury crater. "
    "Propose distinct, concrete, executable analytical approaches and relevant explanatory "
    "mechanisms or alternatives. "
    "Write entirely in English, aiming for 200-300 words; no required number of ideas. "
    "Prioritize relevant ideas that can be explained within this length. "
    "State each distinct approach or explanation once. Merge overlapping ideas. "
    "Avoid repeated hypothesis templates, paraphrases, recaps and routine steps. "
    "For each retained idea, briefly state its test or evidence need and main limitation. "
    "When the distinct ideas are covered, end the answer immediately; leave unused space. "
    "Separate proposed analysis, hypotheses, observations and analyses actually performed. "
    "Claim measurements or observations only when supplied evidence supports them. "
    "Crosses, axes, legends and profile markers are presentation annotations. "
    "Optical imagery and the DEM share MDIS ancestry; account for their correlated origins. "
    "A single catalogue record cannot support population correlations. "
    "Use only the fields actually supplied; missing measurements remain unknown. "
    "Numeric raster processing requires additional tools; describe it as proposed work. "
    "Without evidence, propose relevant investigations and identify evidence needs."
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
