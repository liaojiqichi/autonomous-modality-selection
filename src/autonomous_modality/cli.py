"""CLI demonstration of Mercury crater input-modality selection."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from autonomous_modality.models import (
    AssetAvailability,
    CraterQuestion,
    CraterQuestionType,
    CraterReference,
    DataAssetProfile,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
    SpatialCoverage,
)
from autonomous_modality.selection import select_baseline

METADATA_ONLY_NOTICE = (
    "Metadata-only example; no corresponding scientific data has been loaded or verified."
)
CASE_SPECIFIC_NOTICE = (
    "CASE_SPECIFIC requires verification for the target case; it does not mean data was acquired."
)


def mercury_demo_assets() -> list[DataAssetProfile]:
    """Return metadata-only example assets, not fabricated scientific observations."""
    global_coverage = SpatialCoverage(
        minimum_latitude=-90.0,
        maximum_latitude=90.0,
        minimum_longitude=-180.0,
        maximum_longitude=180.0,
        longitude_direction="positive east",
        latitude_type="planetocentric",
    )
    return [
        DataAssetProfile(
            asset_id="mdis-loi-global-166m",
            modality=InputDataModality.OPTICAL_IMAGE,
            title="MESSENGER MDIS LOI Global Mosaic",
            data_format="GeoTIFF",
            spatial_coverage=global_coverage,
            spatial_resolution_m=166.31,
            model_representations=["crater-centred crop", "regional context crop"],
            analytical_capabilities=["visible morphology", "ejecta-pattern analysis"],
            explanatory_capabilities=["morphological perspective"],
            limitations=[METADATA_ONLY_NOTICE, "single-band 8-bit stretched reflectance"],
            estimated_cost=2.0,
        ),
        DataAssetProfile(
            asset_id="herrick-mercury-craters",
            modality=InputDataModality.CRATER_CATALOG,
            title="Mercury Global Crater Database",
            data_format="CSV",
            spatial_coverage=global_coverage,
            model_representations=["structured JSON record"],
            analytical_capabilities=["diameter comparison", "population analysis"],
            explanatory_capabilities=["regional comparison perspective"],
            limitations=[METADATA_ONLY_NOTICE, "morphology descriptors have limited reliability"],
            estimated_cost=1.0,
        ),
        DataAssetProfile(
            asset_id="mercury-topography-placeholder",
            modality=InputDataModality.TOPOGRAPHY,
            title="Mercury topographic data",
            availability=AssetAvailability.CASE_SPECIFIC,
            model_representations=["hillshade", "elevation profile"],
            analytical_capabilities=["morphometric analysis", "slope analysis"],
            explanatory_capabilities=["topographic perspective"],
            limitations=[METADATA_ONLY_NOTICE, CASE_SPECIFIC_NOTICE],
            estimated_cost=2.0,
        ),
        DataAssetProfile(
            asset_id="caloris-literature-context",
            modality=InputDataModality.SCIENTIFIC_LITERATURE,
            title="Curated Caloris literature context",
            availability=AssetAvailability.CASE_SPECIFIC,
            model_representations=["structured text excerpts"],
            analytical_capabilities=["hypothesis comparison"],
            explanatory_capabilities=[
                "impact-parameter perspective",
                "interior-structure perspective",
            ],
            limitations=[METADATA_ONLY_NOTICE, CASE_SPECIFIC_NOTICE],
            estimated_cost=1.0,
        ),
        DataAssetProfile(
            asset_id="caloris-simulation-placeholder",
            modality=InputDataModality.SIMULATION_OUTPUT,
            title="Caloris SPH simulation outputs",
            availability=AssetAvailability.UNAVAILABLE,
            analytical_capabilities=["simulation comparison"],
            explanatory_capabilities=["impact-process perspective"],
            limitations=[METADATA_ONLY_NOTICE, "no concrete simulation asset has been acquired"],
            estimated_cost=3.0,
        ),
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Select input data modalities for a Mercury crater question."
    )
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--question-type",
        choices=tuple(item.value for item in CraterQuestionType),
        default=CraterQuestionType.GENERAL_CRATER_INVESTIGATION.value,
    )
    parser.add_argument(
        "--crater-name",
        choices=["Caloris"],
        help=(
            "This metadata-only demo has coordinates for Caloris only; "
            "use the pilot for real targets."
        ),
    )
    parser.add_argument("--maximum-modalities", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--maximum-total-cost", type=float)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one metadata-only demonstration and emit a JSON selection decision."""
    args = build_parser().parse_args(argv)
    request = InputSelectionRequest(
        question=CraterQuestion(
            question_id="cli-question",
            text=args.question,
            question_type=CraterQuestionType(args.question_type),
            crater=(
                CraterReference(
                    name=args.crater_name,
                    latitude=30.5,
                    longitude=162.7,
                    diameter_km=1550.0,
                )
                if args.crater_name
                else None
            ),
        ),
        assets=mercury_demo_assets(),
        constraints=InputSelectionConstraints(
            maximum_modalities=args.maximum_modalities,
            maximum_total_cost=args.maximum_total_cost,
        ),
    )
    print(select_baseline(request).model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
