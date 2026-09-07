"""Four primary conditions, offline preparation, and isolated answer inputs."""

from __future__ import annotations

import argparse
import json
import random
from enum import StrEnum
from itertools import combinations
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from autonomous_modality.models import (
    AssetAvailability,
    CraterQuestion,
    CraterReference,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
    NonEmptyString,
    StrictModel,
)


class ExperimentCondition(StrEnum):
    """Primary comparisons; deterministic rules remain auxiliary."""

    NO_DATA = "NO_DATA"
    ALL_AVAILABLE = "ALL_AVAILABLE"
    RANDOM = "RANDOM"
    AGENT = "AGENT"


class ExperimentSelection(StrictModel):
    """An intentional empty control is distinct from failure or pending inference."""

    schema_version: Literal["experiment-selection-1.0"] = "experiment-selection-1.0"
    condition: ExperimentCondition
    status: Literal["ready", "pending_agent", "infeasible"]
    selected_asset_ids: list[NonEmptyString] = Field(default_factory=list)
    total_cost: float = Field(default=0, ge=0)
    seed: int = Field(ge=0)
    reason_codes: list[NonEmptyString] = Field(min_length=1)
    llm_called: Literal[False] = False

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        """Reject ambiguous and contradictory preparation records."""
        if len(set(self.selected_asset_ids)) != len(self.selected_asset_ids):
            raise ValueError("duplicate selected asset IDs")
        if self.status != "ready" or self.condition == ExperimentCondition.NO_DATA:
            if self.selected_asset_ids or self.total_cost:
                raise ValueError("empty or unresolved condition cannot contain selected evidence")
        elif not self.selected_asset_ids:
            raise ValueError("ready data condition requires evidence")
        if self.status == "pending_agent" and self.condition != ExperimentCondition.AGENT:
            raise ValueError("only agent selection can be pending")
        if self.condition == ExperimentCondition.AGENT and self.status == "ready":
            raise ValueError("offline preparation cannot claim an agent decision")
        return self


def prepare_condition(
    request: InputSelectionRequest, condition: ExperimentCondition, seed: int = 0
) -> ExperimentSelection:
    """Sample uniformly over nonempty feasible subsets; never impersonate an agent.

    All-available ignores the selection budget and count cap, but respects asset
    availability and prohibitions. It is a separate, non-budget-matched reference.
    No-data intentionally bypasses required-data constraints as a control.
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    constraints = request.constraints
    assets = sorted(
        (
            a
            for a in request.assets
            if a.availability == AssetAvailability.AVAILABLE
            and a.modality not in constraints.forbidden_modalities
        ),
        key=lambda a: a.asset_id,
    )
    base = {"condition": condition, "seed": seed}
    if condition == ExperimentCondition.NO_DATA:
        return ExperimentSelection(**base, status="ready", reason_codes=["NO_DATA_CONTROL"])
    if not constraints.required_modalities.issubset(a.modality for a in assets):
        return ExperimentSelection(
            **base, status="infeasible", reason_codes=["REQUIRED_ASSET_NOT_AVAILABLE"]
        )
    if condition == ExperimentCondition.ALL_AVAILABLE:
        if not assets:
            return ExperimentSelection(
                **base, status="infeasible", reason_codes=["NO_AVAILABLE_ASSETS"]
            )
        chosen = assets
        reasons = ["ALL_AVAILABLE_NON_BUDGET_MATCHED"]
    else:
        feasible = [
            group
            for count in range(1, min(len(assets), constraints.maximum_modalities) + 1)
            for group in combinations(assets, count)
            if constraints.required_modalities.issubset(a.modality for a in group)
            and (
                constraints.maximum_total_cost is None
                or sum(a.estimated_cost for a in group) <= constraints.maximum_total_cost
            )
        ]
        if not feasible:
            return ExperimentSelection(
                **base, status="infeasible", reason_codes=["NO_FEASIBLE_SUBSET"]
            )
        if condition == ExperimentCondition.AGENT:
            return ExperimentSelection(
                **base, status="pending_agent", reason_codes=["AGENT_NOT_CONNECTED"]
            )
        if condition != ExperimentCondition.RANDOM:
            raise ValueError("unsupported experiment condition")
        chosen = list(random.Random(seed).choice(feasible))
        reasons = ["UNIFORM_FEASIBLE_SUBSET_SAMPLE"]
    return ExperimentSelection(
        **base,
        status="ready",
        selected_asset_ids=[a.asset_id for a in chosen],
        total_cost=sum(a.estimated_cost for a in chosen),
        reason_codes=reasons,
    )


class AnswerInput(StrictModel):
    """Whitelist for future generation: no scores, full inventory, or control label."""

    question: CraterQuestion
    answer_requirements: list[NonEmptyString]
    evidence_paths: list[NonEmptyString]


class ExperimentEvidence(StrictModel):
    """Pinned selected evidence; representation does not define modality."""

    path: NonEmptyString
    modality: InputDataModality
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    representation: NonEmptyString
    units: NonEmptyString


class ExperimentRecord(StrictModel):
    """Decision inventory and generation whitelist remain separate."""

    request: InputSelectionRequest
    selection: ExperimentSelection
    answer_input: AnswerInput | None
    evidence: list[ExperimentEvidence]
    package: NonEmptyString
    package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_routing(self) -> Self:
        """Reject evidence or generator payloads for unresolved conditions."""
        if (self.answer_input is not None) != (self.selection.status == "ready"):
            raise ValueError("answer input must match readiness")
        chosen = {
            a.modality
            for a in self.request.assets
            if a.asset_id in self.selection.selected_asset_ids
        }
        if len(chosen) != len(self.selection.selected_asset_ids):
            raise ValueError("unknown selected asset")
        if {f.modality for f in self.evidence} != chosen:
            raise ValueError("evidence differs from selection")
        if self.answer_input is not None:
            if self.answer_input.question != self.request.question:
                raise ValueError("question differs from request")
            expected_paths = [
                str((Path(self.package).parent / f.path).resolve()) for f in self.evidence
            ]
            if self.answer_input.evidence_paths != expected_paths:
                raise ValueError("answer evidence paths mismatch")
        return self


class PreparationRun(StrictModel):
    """Versioned offline run; no generated answers or model results implied."""

    protocol_version: Literal["richness-four-conditions-1.0"] = "richness-four-conditions-1.0"
    question_version: NonEmptyString
    questions_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    code_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    constraints: InputSelectionConstraints
    cost_unit: Literal["ordinal engineering units; not tokens, time or money"] = (
        "ordinal engineering units; not tokens, time or money"
    )
    llm_called: Literal[False] = False
    answers_generated: Literal[0] = 0
    records: list[ExperimentRecord] = Field(min_length=1)


def main() -> None:
    """Prepare four conditions from verified existing packages, without inference."""
    from autonomous_modality.acquisition import sha256_file
    from autonomous_modality.benchmark import QuestionSet, verify_package

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--questions", type=Path, default=Path("configs/mercury_questions_v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=float, default=3)
    parser.add_argument("--maximum-modalities", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    constraints = InputSelectionConstraints(
        maximum_total_cost=args.budget, maximum_modalities=args.maximum_modalities
    )
    output = args.output.resolve()
    if output.exists() or "raw" in {p.lower() for p in output.parts}:
        raise ValueError("output must be a new directory outside raw")
    questions = QuestionSet.model_validate_json(args.questions.read_text(encoding="utf-8"))
    if any(q.quantitative_prerequisites or q.quantitative_modalities for q in questions.questions):
        raise ValueError("quantitative inversion questions are outside the active protocol")
    manifests = sorted(args.benchmark.glob("crater-*/package.json"))
    if not manifests:
        raise ValueError("no evidence packages found")
    records = []
    for manifest in manifests:
        package = verify_package(manifest.parent)
        for spec in questions.questions:
            question = CraterQuestion(
                question_id=f"{package.case.id}-{spec.question_id}",
                text=spec.text.replace("{crater}", package.case.name),
                question_type=spec.question_type,
                crater=CraterReference(
                    name=package.case.name,
                    latitude=package.case.lat_n,
                    longitude=package.case.lon_e_0,
                ),
            )
            request = InputSelectionRequest(
                question=question, assets=package.assets, constraints=constraints
            )
            for condition in ExperimentCondition:
                result = prepare_condition(request, condition, args.seed)
                modalities = {
                    a.modality for a in package.assets if a.asset_id in result.selected_asset_ids
                }
                files = [f for f in package.files if f.modality in modalities]
                answer = (
                    None
                    if result.status != "ready"
                    else AnswerInput(
                        question=question,
                        answer_requirements=spec.answer_requirements,
                        evidence_paths=[str((manifest.parent / f.path).resolve()) for f in files],
                    )
                )
                records.append(
                    ExperimentRecord(
                        request=request,
                        selection=result,
                        answer_input=answer,
                        evidence=[
                            ExperimentEvidence(
                                path=f.path,
                                modality=f.modality,
                                sha256=f.sha256,
                                representation=f.representation,
                                units=f.units,
                            )
                            for f in files
                        ],
                        package=str(manifest.resolve()),
                        package_sha256=sha256_file(manifest),
                    )
                )
    output.mkdir(parents=True)
    payload = PreparationRun(
        question_version=questions.version,
        questions_sha256=sha256_file(args.questions),
        code_sha256=sha256_file(Path(__file__)),
        constraints=constraints,
        records=records,
    )
    (output / "preparation.json").write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps({"prepared": len(records), "answers_generated": 0}))


if __name__ == "__main__":
    main()
