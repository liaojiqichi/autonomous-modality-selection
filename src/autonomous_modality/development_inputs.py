"""Content declarations for the existing Mercury development views, without values.

Apply only to the current catalogue/local-context-image/terrain-summary adapters.
These declarations describe model-visible representations, not new scientific data.
"""

from autonomous_modality.modality_descriptions import ASSET_DESCRIPTION_VERSION, modality_inventory
from autonomous_modality.models import AssetContentInventory, InputDataModality

INVENTORY_VERSION = ASSET_DESCRIPTION_VERSION
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
ANSWER_POLICY_VERSION = "english-ap-input-supported-1.1"
ANSWER_POLICY = (
    "Assist an exploratory study of a Mercury crater. "
    "Write in English within 200-300 words, including headings. "
    "Use concise paragraphs or bullets, with no fixed number of ideas. "
    "Prioritize distinct analytical tests feasible with supplied representations and "
    "plausible explanations anchored in supplied features or representation limitations. "
    "Later computation is allowed; hypotheses need not be proven. "
    "State each idea once, with its evidence basis and essential qualification. "
    "Combine shared qualifications. Omit an introductory summary, repeated input "
    "descriptions and a concluding recap. End after the substantive points. "
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
    """Return the shared current inventory through the existing public interface."""
    try:
        return modality_inventory(modality)
    except ValueError as exc:
        raise ValueError("No development-view inventory is defined for this modality") from exc
