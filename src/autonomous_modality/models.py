"""Strict contracts for task-adaptive scientific input-modality selection."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

CURRENT_SCHEMA_VERSION = "2.0"
NonEmptyString = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
UnitScore = Annotated[float, Field(ge=0.0, le=1.0)]
ExpertRating = Annotated[int, Field(ge=1, le=5)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


class InputDataModality(StrEnum):
    """Closed taxonomy of scientific evidence available to the selector."""

    OPTICAL_IMAGE = "OPTICAL_IMAGE"
    CRATER_CATALOG = "CRATER_CATALOG"
    TOPOGRAPHY = "TOPOGRAPHY"
    SCIENTIFIC_LITERATURE = "SCIENTIFIC_LITERATURE"
    SIMULATION_OUTPUT = "SIMULATION_OUTPUT"


class CraterQuestionType(StrEnum):
    """Question intents aligned with the three solution-richness dimensions."""

    ANALYTICAL_APPROACH_DISCOVERY = "ANALYTICAL_APPROACH_DISCOVERY"
    EXPLANATORY_PERSPECTIVE_EXPLORATION = "EXPLANATORY_PERSPECTIVE_EXPLORATION"
    CROSS_MODAL_RELATIONSHIP_DISCOVERY = "CROSS_MODAL_RELATIONSHIP_DISCOVERY"
    GENERAL_CRATER_INVESTIGATION = "GENERAL_CRATER_INVESTIGATION"


class AssetAvailability(StrEnum):
    """Declared availability; CASE_SPECIFIC needs case-level verification, not acquisition."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    CASE_SPECIFIC = "CASE_SPECIFIC"


class SelectionPriority(StrEnum):
    """Importance assigned to a selected input modality."""

    REQUIRED = "REQUIRED"
    COMPLEMENTARY = "COMPLEMENTARY"


class CrossModalInsightLevel(StrEnum):
    """Degree of integration expressed by a cross-modal statement."""

    JUXTAPOSITION = "JUXTAPOSITION"
    CORRESPONDENCE = "CORRESPONDENCE"
    SYNTHESIS = "SYNTHESIS"


class StrictModel(BaseModel):
    """Base contract that rejects schema drift and validates assignment."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=False,
        allow_inf_nan=False,
    )


class SpatialCoverage(StrictModel):
    """Planetary-coordinate coverage of a data asset."""

    target_body: NonEmptyString = "Mercury"
    minimum_latitude: Annotated[float, Field(ge=-90.0, le=90.0)] | None = None
    maximum_latitude: Annotated[float, Field(ge=-90.0, le=90.0)] | None = None
    minimum_longitude: Annotated[float, Field(ge=-180.0, le=360.0)] | None = None
    maximum_longitude: Annotated[float, Field(ge=-180.0, le=360.0)] | None = None
    longitude_direction: str | None = None
    latitude_type: str | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Reject inverted coordinate ranges."""
        if (
            self.minimum_latitude is not None
            and self.maximum_latitude is not None
            and self.minimum_latitude > self.maximum_latitude
        ):
            raise ValueError("minimum latitude must not exceed maximum latitude")
        if (
            self.minimum_longitude is not None
            and self.maximum_longitude is not None
            and self.minimum_longitude > self.maximum_longitude
        ):
            raise ValueError("minimum longitude must not exceed maximum longitude")
        return self


class DataAssetProfile(StrictModel):
    """Metadata describing one available source of scientific evidence."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    asset_id: NonEmptyString
    modality: InputDataModality
    title: NonEmptyString
    availability: AssetAvailability = AssetAvailability.AVAILABLE
    source_uri: str | None = None
    data_format: str | None = None
    spatial_coverage: SpatialCoverage | None = None
    spatial_resolution_m: Annotated[float, Field(gt=0.0)] | None = None
    model_representations: list[NonEmptyString] = Field(default_factory=list)
    analytical_capabilities: list[NonEmptyString] = Field(default_factory=list)
    explanatory_capabilities: list[NonEmptyString] = Field(default_factory=list)
    limitations: list[NonEmptyString] = Field(default_factory=list)
    estimated_cost: NonNegativeFloat = 1.0
    quality_score: UnitScore | None = None


class CraterReference(StrictModel):
    """Catalogue-compatible identity and location of a target crater."""

    crater_id: str | None = None
    name: str | None = None
    latitude: Annotated[float, Field(ge=-90.0, le=90.0)]
    longitude: Annotated[float, Field(ge=-180.0, le=360.0)]
    diameter_km: Annotated[float, Field(gt=0.0)] | None = None
    longitude_direction: NonEmptyString = "positive east"
    latitude_type: NonEmptyString = "planetocentric"


class CraterQuestion(StrictModel):
    """One crater-related research question presented to the selector."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    question_id: NonEmptyString
    text: NonEmptyString
    question_type: CraterQuestionType
    crater: CraterReference | None = None
    target_body: NonEmptyString = "Mercury"
    target_aspects: list[NonEmptyString] = Field(default_factory=list)


class InputSelectionConstraints(StrictModel):
    """Hard resource limits and soft preferences for input-data selection."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    maximum_modalities: Annotated[int, Field(ge=1, le=5)] = 3
    maximum_total_cost: NonNegativeFloat | None = None
    required_modalities: set[InputDataModality] = Field(default_factory=set)
    forbidden_modalities: set[InputDataModality] = Field(default_factory=set)
    preferred_modalities: list[InputDataModality] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_constraints(self) -> Self:
        """Reject internally inconsistent modality constraints."""
        if self.required_modalities & self.forbidden_modalities:
            raise ValueError("a modality cannot be both required and forbidden")
        if len(self.required_modalities) > self.maximum_modalities:
            raise ValueError("required modalities exceed maximum_modalities")
        if len(self.preferred_modalities) != len(set(self.preferred_modalities)):
            raise ValueError("preferred modalities must be unique")
        if set(self.preferred_modalities) & self.forbidden_modalities:
            raise ValueError("a forbidden modality cannot be preferred")
        return self


class InputSelectionRequest(StrictModel):
    """Complete input to an input-modality selection agent."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    question: CraterQuestion
    assets: list[DataAssetProfile] = Field(min_length=1)
    constraints: InputSelectionConstraints = Field(default_factory=InputSelectionConstraints)

    @model_validator(mode="after")
    def ensure_unique_modalities(self) -> Self:
        """Keep the first prototype to one concrete asset per modality."""
        modalities = [asset.modality for asset in self.assets]
        if len(modalities) != len(set(modalities)):
            raise ValueError("request assets must have unique modalities")
        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("request assets must have unique asset IDs")
        return self


class ModalityExclusion(StrictModel):
    """A scientific input modality rejected by one or more hard rules."""

    modality: InputDataModality
    reason_codes: list[NonEmptyString] = Field(min_length=1)
    messages: list[NonEmptyString] = Field(min_length=1)


class CandidateFilterResult(StrictModel):
    """Feasible assets and auditable hard-rule exclusions."""

    rule_version: NonEmptyString
    available_assets: list[DataAssetProfile] = Field(min_length=1)
    exclusions: list[ModalityExclusion] = Field(default_factory=list)


class ModalityScore(StrictModel):
    """Deterministic base score for one feasible scientific modality."""

    modality: InputDataModality
    score: float
    reason_codes: list[NonEmptyString] = Field(default_factory=list)


class SelectedInputModality(StrictModel):
    """One selected modality and its expected contribution to richness."""

    modality: InputDataModality
    asset_id: NonEmptyString
    priority: SelectionPriority
    expected_analytical_approaches: list[NonEmptyString] = Field(default_factory=list)
    expected_explanatory_perspectives: list[NonEmptyString] = Field(default_factory=list)
    reason_codes: list[NonEmptyString] = Field(min_length=1)


class ExpectedCrossModalInsight(StrictModel):
    """An anticipated relationship enabled by a pair of selected modalities."""

    modalities: set[InputDataModality] = Field(min_length=2)
    description: NonEmptyString


class ExpectedRichnessProfile(StrictModel):
    """Predicted richness dimensions enabled by the selected evidence."""

    analytical_approaches: list[NonEmptyString] = Field(default_factory=list)
    explanatory_perspectives: list[NonEmptyString] = Field(default_factory=list)
    cross_modal_insights: list[ExpectedCrossModalInsight] = Field(default_factory=list)


class InputSelectionDecision(StrictModel):
    """Selected scientific input modalities for a crater question."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    selected: list[SelectedInputModality] = Field(min_length=1, max_length=5)
    expected_richness: ExpectedRichnessProfile
    total_cost: NonNegativeFloat
    rationale: NonEmptyString
    reason_codes: list[NonEmptyString] = Field(min_length=1)
    unanswerable_aspects: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_unique_selection(self) -> Self:
        """Reject repeated modalities in the selected evidence set."""
        modalities = [item.modality for item in self.selected]
        if len(modalities) != len(set(modalities)):
            raise ValueError("selected modalities must be unique")
        return self


class BaselineSelectionResult(StrictModel):
    """Complete deterministic input-selection result."""

    rule_version: NonEmptyString
    candidates: CandidateFilterResult
    scores: list[ModalityScore] = Field(min_length=1)
    decision: InputSelectionDecision


class CrossModalInsight(StrictModel):
    """One cross-modal statement extracted from a generated solution."""

    modalities: set[InputDataModality] = Field(min_length=2)
    description: NonEmptyString
    level: CrossModalInsightLevel


class SolutionRichnessAnnotation(StrictModel):
    """Expert or structured annotation of the three richness dimensions."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    scenario_id: NonEmptyString
    solution_id: NonEmptyString
    annotator_id: NonEmptyString
    analytical_approaches: list[NonEmptyString] = Field(default_factory=list)
    explanatory_perspectives: list[NonEmptyString] = Field(default_factory=list)
    cross_modal_insights: list[CrossModalInsight] = Field(default_factory=list)
    analytical_approach_rating: ExpertRating | None = None
    explanatory_perspective_rating: ExpertRating | None = None
    cross_modal_insight_rating: ExpertRating | None = None
    notes: str | None = None


class RichnessScores(StrictModel):
    """Deterministic counts derived from one richness annotation."""

    # Legacy scores have no rule version; do not silently label them as recomputed.
    rule_version: NonEmptyString | None = None
    analytical_approach_count: Annotated[int, Field(ge=0)]
    explanatory_perspective_count: Annotated[int, Field(ge=0)]
    cross_modal_correspondence_count: Annotated[int, Field(ge=0)]
    cross_modal_synthesis_count: Annotated[int, Field(ge=0)]
    weighted_cross_modal_score: NonNegativeFloat


class EvaluationScenario(StrictModel):
    """A reproducible question, asset inventory, and experimental condition."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    scenario_id: NonEmptyString
    request: InputSelectionRequest
    condition_id: NonEmptyString
    tags: set[NonEmptyString] = Field(default_factory=set)
