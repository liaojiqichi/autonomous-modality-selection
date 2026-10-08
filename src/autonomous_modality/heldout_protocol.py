"""Versioned held-out scientific design, with deployment validation kept separate."""

from __future__ import annotations

import hashlib
import random
from itertools import combinations
from typing import Literal, Self

from pydantic import Field, model_validator

from autonomous_modality.benchmark import QuestionSet
from autonomous_modality.experiments import scenario_seed
from autonomous_modality.heldout import Cohort
from autonomous_modality.models import StrictModel

COSTS = {"CRATER_CATALOG": 1, "OPTICAL_IMAGE": 2, "TOPOGRAPHY": 2, "MULTISPECTRAL_IMAGE": 2}
MODELS = ("Qwen/Qwen3-VL-8B-Instruct", "google/gemma-4-E4B-it")
PRIMARY = ("NO_DATA", "ALL_AVAILABLE", "RANDOM", "AGENT_ITERATIVE")


class FrozenProtocol(StrictModel):
    """Scientific design can be frozen before checkpoint-specific GPU approval."""

    version: Literal["heldout-four-modality-ap-1.0"] = "heldout-four-modality-ap-1.0"
    design_frozen: Literal[True] = True
    runtime_approved: Literal[False] = False
    revision_authority: str = "User approved ordinal costs on 2026-10-08 in this chat."
    cost_unit: Literal["legacy_ordinal_units"] = "legacy_ordinal_units"
    costs: dict[str, int] = Field(default_factory=lambda: dict(COSTS))
    primary_budget: Literal[4] = 4
    sensitivity_budget: Literal[3] = 3
    maximum_modalities: Literal[2] = 2
    maximum_selector_calls: Literal[2] = 2
    random_draws: Literal[5] = 5
    seed: Literal[42] = 42
    image_edge: Literal[448] = 448
    profile_samples: Literal[17] = 17
    selector_tokens: Literal[512] = 512
    answer_tokens: Literal[1024] = 1024
    maximum_input_tokens: Literal[8192] = 8192
    answer_repetition_penalty: Literal[1.2] = 1.2
    decoding: Literal["greedy_one_beam"] = "greedy_one_beam"
    primary_conditions: tuple[str, ...] = PRIMARY
    auxiliary_conditions: tuple[Literal["AGENT"]] = ("AGENT",)
    models: tuple[str, ...] = MODELS
    target_count: Literal[30] = 30
    question_count: Literal[4] = 4
    primary_answer_attempts: Literal[1920] = 1920
    primary_with_ablation_attempts: Literal[2160] = 2160
    sensitivity_with_ablation_attempts: Literal[2160] = 2160
    question_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cohort_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pinned_files: dict[str, str]
    decisions: tuple[str, ...] = (
        "Four modalities; multispectral evidence is four-region eight-band numeric text.",
        "Primary agent is iterative; one-shot AGENT is an auxiliary ablation.",
        "Cumulative acquisition costs; no refunds or hidden retries; stop reasons remain distinct.",
        "ALL_AVAILABLE uses all four modalities, cost 7, without selection caps.",
        "RANDOM samples uniformly from nonempty feasible subsets with replacement.",
        "Five shared draws per scenario and budget; repeated choices remain separate attempts.",
        "Primary outcomes are separate input-supported A and P counts; also report raw A/P.",
        "Scientific validity and evidence fidelity are separate checks, not score filters.",
        "Exclude literature tools, generated target descriptions and review notes from answers.",
        "Retain allocated targets with quality flags; no unrecorded target substitutions.",
        "No target-specific enhancement, geological segmentation or centre correction is applied.",
        "Input-supported means feasible with supplied evidence; later computation is allowed.",
        "Record failures and truncation by condition; failed outputs have no richness score.",
        "Mean RANDOM draws within scenario; paired effects aggregate with equal crater weights.",
        "Report successful pair counts, incomplete random-draw sets and missingness explicitly.",
        "64 preselected human review slots; up to 16 diagnostic examples kept separate.",
        "Before inference pin BOTH checkpoint revisions, processors, quantization and software; "
        "validate the fixed representations on development targets only.",
        "Evaluator identity, configuration and calibrated rubric implementation require a separate "
        "execution lock before held-out annotation; no held-out calibration.",
        "Changes to prompts, limits, representations or frozen artifacts require a new version.",
    )

    @model_validator(mode="after")
    def fixed_design(self) -> Self:
        """Reject changes disguised as the same frozen protocol version."""
        if self.costs != COSTS or self.models != MODELS or self.primary_conditions != PRIMARY:
            raise ValueError("FROZEN_DESIGN_CHANGED")
        return self


class Scenario(StrictModel):
    case_id: int
    question_id: str
    question: str
    answer_requirements: list[str]
    random_budget_4: list[list[str]]
    random_budget_3: list[list[str]]


class HumanReviewSlot(StrictModel):
    model: str
    condition: str
    question_id: str
    case_id: int
    draw: int
    budget: Literal[4] = 4


class Design(StrictModel):
    scenarios: list[Scenario] = Field(min_length=120, max_length=120)
    human_review_slots: list[HumanReviewSlot] = Field(min_length=64, max_length=64)
    llm_called: Literal[False] = False


def options(budget: int) -> list[list[str]]:
    """Enumerate notebook-compatible nonempty feasible subsets in stable order."""
    if budget not in (3, 4):
        raise ValueError("Unsupported frozen budget")
    return [
        list(group)
        for n in (1, 2)
        for group in combinations(sorted(COSTS), n)
        if sum(COSTS[m] for m in group) <= budget
    ]


def freeze_design(cohort: Cohort, questions: QuestionSet) -> Design:
    """Prepare shared draws and human review slots without generating responses."""
    if len(questions.questions) != 4:
        raise ValueError("Exactly four frozen questions required")
    scenarios = []
    for target in cohort.targets:
        for question in questions.questions:
            draws = {
                b: [
                    random.Random(
                        scenario_seed(42, f"{target.id}-{question.question_id}", b, d)
                    ).choice(options(b))
                    for d in range(5)
                ]
                for b in (3, 4)
            }
            scenarios.append(
                Scenario(
                    case_id=target.id,
                    question_id=question.question_id,
                    question=question.text.replace("{crater}", target.name),
                    answer_requirements=question.answer_requirements,
                    random_budget_4=draws[4],
                    random_budget_3=draws[3],
                )
            )
    slots = []
    for model in MODELS:
        for condition in PRIMARY:
            for question in questions.questions:
                prefix = f"human-review-20261008:{model}:{condition}:{question.question_id}"
                ranked = sorted(
                    cohort.targets,
                    key=lambda t: hashlib.sha256(f"{prefix}:{t.id}".encode()).hexdigest(),
                )
                for target in ranked[:2]:
                    draw = (
                        (
                            int(
                                hashlib.sha256(f"{prefix}:{target.id}:draw".encode()).hexdigest(),
                                16,
                            )
                            % 5
                            + 1
                        )
                        if condition == "RANDOM"
                        else 1
                    )
                    slots.append(
                        HumanReviewSlot(
                            model=model,
                            condition=condition,
                            question_id=question.question_id,
                            case_id=target.id,
                            draw=draw,
                        )
                    )
    return Design(scenarios=scenarios, human_review_slots=slots)
