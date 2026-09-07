"""Deterministic baseline for selecting richness-producing input modalities."""

from __future__ import annotations

from itertools import combinations

from autonomous_modality.models import (
    AssetAvailability,
    BaselineSelectionResult,
    CandidateFilterResult,
    CraterQuestionType,
    DataAssetProfile,
    ExpectedCrossModalInsight,
    ExpectedRichnessProfile,
    InputDataModality,
    InputSelectionDecision,
    InputSelectionRequest,
    ModalityExclusion,
    ModalityScore,
    SelectedInputModality,
    SelectionPriority,
)

RULE_VERSION = "input-richness-baseline-1.2"
MODALITY_ORDER = tuple(InputDataModality)

TASK_SCORES: dict[CraterQuestionType, dict[InputDataModality, float]] = {
    CraterQuestionType.ANALYTICAL_APPROACH_DISCOVERY: {
        InputDataModality.OPTICAL_IMAGE: 75.0,
        InputDataModality.CRATER_CATALOG: 65.0,
        InputDataModality.TOPOGRAPHY: 85.0,
        InputDataModality.SCIENTIFIC_LITERATURE: 55.0,
        InputDataModality.SIMULATION_OUTPUT: 70.0,
    },
    CraterQuestionType.EXPLANATORY_PERSPECTIVE_EXPLORATION: {
        InputDataModality.OPTICAL_IMAGE: 50.0,
        InputDataModality.CRATER_CATALOG: 35.0,
        InputDataModality.TOPOGRAPHY: 55.0,
        InputDataModality.SCIENTIFIC_LITERATURE: 100.0,
        InputDataModality.SIMULATION_OUTPUT: 90.0,
    },
    CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY: {
        InputDataModality.OPTICAL_IMAGE: 75.0,
        InputDataModality.CRATER_CATALOG: 60.0,
        InputDataModality.TOPOGRAPHY: 80.0,
        InputDataModality.SCIENTIFIC_LITERATURE: 45.0,
        InputDataModality.SIMULATION_OUTPUT: 55.0,
    },
    CraterQuestionType.GENERAL_CRATER_INVESTIGATION: {
        InputDataModality.OPTICAL_IMAGE: 80.0,
        InputDataModality.CRATER_CATALOG: 60.0,
        InputDataModality.TOPOGRAPHY: 80.0,
        InputDataModality.SCIENTIFIC_LITERATURE: 70.0,
        InputDataModality.SIMULATION_OUTPUT: 65.0,
    },
}

PAIR_INSIGHTS: dict[frozenset[InputDataModality], str] = {
    frozenset({InputDataModality.OPTICAL_IMAGE, InputDataModality.CRATER_CATALOG}): (
        "Relate catalogue morphology and diameter to visible crater structure."
    ),
    frozenset({InputDataModality.OPTICAL_IMAGE, InputDataModality.TOPOGRAPHY}): (
        "Distinguish topographic relief from illumination or albedo patterns."
    ),
    frozenset({InputDataModality.CRATER_CATALOG, InputDataModality.TOPOGRAPHY}): (
        "Combine catalogue diameter with elevation-derived morphometry."
    ),
    frozenset({InputDataModality.TOPOGRAPHY, InputDataModality.SIMULATION_OUTPUT}): (
        "Compare observed basin structure with simulated impact outcomes."
    ),
    frozenset({InputDataModality.SCIENTIFIC_LITERATURE, InputDataModality.SIMULATION_OUTPUT}): (
        "Relate published formation hypotheses to simulated parameter families."
    ),
    frozenset({InputDataModality.OPTICAL_IMAGE, InputDataModality.SCIENTIFIC_LITERATURE}): (
        "Connect visible morphology with published explanatory perspectives."
    ),
}


def filter_candidates(request: InputSelectionRequest) -> CandidateFilterResult:
    """Apply availability, prohibitions, and individual cost constraints."""
    exclusions: list[ModalityExclusion] = []
    available: list[DataAssetProfile] = []
    for asset in request.assets:
        codes: list[str] = []
        messages: list[str] = []
        if asset.availability is AssetAvailability.UNAVAILABLE:
            codes.append("ASSET_UNAVAILABLE")
            messages.append("The concrete data asset is unavailable.")
        if asset.modality in request.constraints.forbidden_modalities:
            codes.append("MODALITY_FORBIDDEN")
            messages.append("The modality is excluded by a hard constraint.")
        budget = request.constraints.maximum_total_cost
        if budget is not None and asset.estimated_cost > budget:
            codes.append("ASSET_EXCEEDS_TOTAL_BUDGET")
            messages.append("The asset alone exceeds the total input budget.")
        if codes:
            exclusions.append(
                ModalityExclusion(
                    modality=asset.modality,
                    reason_codes=codes,
                    messages=messages,
                )
            )
        else:
            available.append(asset)

    if not available:
        raise ValueError("hard constraints leave no available input data modalities")
    available_modalities = {asset.modality for asset in available}
    missing_required = request.constraints.required_modalities - available_modalities
    if missing_required:
        names = ", ".join(sorted(item.value for item in missing_required))
        raise ValueError(f"required modalities are not available: {names}")
    return CandidateFilterResult(
        rule_version=RULE_VERSION,
        available_assets=available,
        exclusions=exclusions,
    )


def _distinct_capabilities(items: list[str]) -> list[str]:
    """Keep first spellings while ignoring case and surrounding whitespace."""
    distinct: dict[str, str] = {}
    for item in items:
        distinct.setdefault(item.strip().casefold(), item.strip())
    return list(distinct.values())


def _base_score(request: InputSelectionRequest, asset: DataAssetProfile) -> ModalityScore:
    score = TASK_SCORES[request.question.question_type][asset.modality]
    reasons = [f"QUESTION_{request.question.question_type.value}_FIT"]
    score += min(len(_distinct_capabilities(asset.analytical_capabilities)), 5) * 3.0
    if asset.analytical_capabilities:
        reasons.append("ADDS_ANALYTICAL_APPROACHES")
    score += min(len(_distinct_capabilities(asset.explanatory_capabilities)), 5) * 3.0
    if asset.explanatory_capabilities:
        reasons.append("ADDS_EXPLANATORY_PERSPECTIVES")
    if asset.quality_score is not None:
        score += asset.quality_score * 5.0
        reasons.append("ASSET_QUALITY_AVAILABLE")
    if asset.modality in request.constraints.preferred_modalities:
        score += 10.0
        reasons.append("SOFT_MODALITY_PREFERENCE")
    return ModalityScore(modality=asset.modality, score=score, reason_codes=reasons)


def _pair_bonus(
    candidate: InputDataModality,
    selected: set[InputDataModality],
    question_type: CraterQuestionType,
) -> float:
    multiplier = (
        1.5 if question_type is CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY else 1.0
    )
    pairs = sum(frozenset({candidate, existing}) in PAIR_INSIGHTS for existing in selected)
    return pairs * 20.0 * multiplier


def _select_assets(
    request: InputSelectionRequest,
    candidates: CandidateFilterResult,
) -> tuple[list[DataAssetProfile], list[ModalityScore], bool]:
    assets_by_modality = {asset.modality: asset for asset in candidates.available_assets}
    base_scores = {
        asset.modality: _base_score(request, asset) for asset in candidates.available_assets
    }
    selected = [
        assets_by_modality[modality]
        for modality in MODALITY_ORDER
        if modality in request.constraints.required_modalities
    ]
    selected_modalities = {asset.modality for asset in selected}
    total_cost = sum(asset.estimated_cost for asset in selected)
    if (
        request.constraints.maximum_total_cost is not None
        and total_cost > request.constraints.maximum_total_cost
    ):
        raise ValueError("required modalities exceed maximum_total_cost")

    while len(selected) < request.constraints.maximum_modalities:
        feasible = [
            asset
            for asset in candidates.available_assets
            if asset.modality not in selected_modalities
            and (
                request.constraints.maximum_total_cost is None
                or total_cost + asset.estimated_cost <= request.constraints.maximum_total_cost
            )
        ]
        if not feasible:
            break
        feasible.sort(
            key=lambda asset: (
                -(
                    base_scores[asset.modality].score
                    + _pair_bonus(
                        asset.modality,
                        selected_modalities,
                        request.question.question_type,
                    )
                ),
                MODALITY_ORDER.index(asset.modality),
            )
        )
        chosen = feasible[0]
        selected.append(chosen)
        selected_modalities.add(chosen.modality)
        total_cost += chosen.estimated_cost

    if not selected:
        raise ValueError("no input modality combination fits the total cost budget")

    used_fallback = False
    if (
        request.question.question_type is CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY
        and len(selected) < 2
    ):
        selected = _find_cross_modal_fallback(request, candidates)
        if not selected:
            raise ValueError("cross-modal relationship discovery requires at least two modalities")
        used_fallback = True
    ranked = sorted(
        base_scores.values(),
        key=lambda item: (-item.score, MODALITY_ORDER.index(item.modality)),
    )
    return selected, ranked, used_fallback


def _find_cross_modal_fallback(
    request: InputSelectionRequest,
    candidates: CandidateFilterResult,
) -> list[DataAssetProfile]:
    """Return the first feasible set by size then taxonomy order, not richness."""
    ordered = sorted(
        candidates.available_assets, key=lambda asset: MODALITY_ORDER.index(asset.modality)
    )
    constraints = request.constraints
    for size in range(2, min(constraints.maximum_modalities, len(ordered)) + 1):
        for group in combinations(ordered, size):
            if not constraints.required_modalities.issubset(asset.modality for asset in group):
                continue
            if (
                constraints.maximum_total_cost is not None
                and sum(asset.estimated_cost for asset in group) > constraints.maximum_total_cost
            ):
                continue
            return sorted(
                group, key=lambda asset: asset.modality not in constraints.required_modalities
            )
    return []


def select_baseline(request: InputSelectionRequest) -> BaselineSelectionResult:
    """Select a budget-feasible set predicted to increase solution richness."""
    candidates = filter_candidates(request)
    assets, scores, used_fallback = _select_assets(request, candidates)
    selected_modalities = {asset.modality for asset in assets}
    insights = [
        ExpectedCrossModalInsight(modalities=set(pair), description=description)
        for pair, description in PAIR_INSIGHTS.items()
        if pair.issubset(selected_modalities)
    ]
    approaches = _distinct_capabilities(
        [item for asset in assets for item in asset.analytical_capabilities]
    )
    perspectives = _distinct_capabilities(
        [item for asset in assets for item in asset.explanatory_capabilities]
    )
    selected = [
        SelectedInputModality(
            modality=asset.modality,
            asset_id=asset.asset_id,
            priority=(
                SelectionPriority.REQUIRED
                if asset.modality in request.constraints.required_modalities
                else SelectionPriority.COMPLEMENTARY
            ),
            expected_analytical_approaches=_distinct_capabilities(asset.analytical_capabilities),
            expected_explanatory_perspectives=_distinct_capabilities(
                asset.explanatory_capabilities
            ),
            reason_codes=[
                *next(score.reason_codes for score in scores if score.modality is asset.modality),
                "SELECTED_WITHIN_MODALITY_AND_COST_BUDGET",
            ],
        )
        for asset in assets
    ]
    rationale = (
        "Selected complementary scientific inputs to expand analytical approaches, "
        "explanatory perspectives, and cross-modal relationships within the constraints."
    )
    reason_codes = ["RICHNESS_ORIENTED_DETERMINISTIC_BASELINE"]
    if used_fallback:
        rationale = (
            "Greedy selection could not satisfy the cross-modal minimum. Selected the first "
            "feasible combination by size and taxonomy order while preserving all hard "
            "constraints; this fallback does not optimize solution richness."
        )
        reason_codes.append("CROSS_MODAL_FEASIBILITY_FALLBACK")
    decision = InputSelectionDecision(
        selected=selected,
        expected_richness=ExpectedRichnessProfile(
            analytical_approaches=approaches,
            explanatory_perspectives=perspectives,
            cross_modal_insights=insights,
        ),
        total_cost=sum(asset.estimated_cost for asset in assets),
        rationale=rationale,
        reason_codes=reason_codes,
    )
    return BaselineSelectionResult(
        rule_version=RULE_VERSION,
        candidates=candidates,
        scores=scores,
        decision=decision,
    )
