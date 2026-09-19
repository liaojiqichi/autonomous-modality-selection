"""Strict final-proposal configuration, independent of timetable reminders."""

from typing import Literal

from pydantic import Field

from autonomous_modality.models import StrictModel


class ExperimentProtocol(StrictModel):
    """Frozen design constants; model revisions must be pinned at execution time."""

    version: Literal["richness-ap-dual-model-2.0"] = "richness-ap-dual-model-2.0"
    proposal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    models: tuple[Literal["Qwen/Qwen3-VL-8B-Instruct"], Literal["google/gemma-4-E4B-it"]]
    primary_budget: Literal[4] = 4
    sensitivity_budget: Literal[3] = 3
    maximum_modalities: Literal[2] = 2
    random_draws: Literal[5] = 5
    development_target_count: Literal[6] = 6
    held_out_target_count: Literal[30] = 30
    question_count: Literal[4] = 4
    human_review_count: Literal[64] = 64
    diagnostic_review_maximum: Literal[16] = 16
    dimensions: tuple[Literal["A"], Literal["P"]] = ("A", "P")
    sampling: Literal["uniform_feasible_subsets_with_replacement"] = (
        "uniform_feasible_subsets_with_replacement"
    )
    answer_decoding: Literal["greedy"] = "greedy"
    schedule_policy: Literal["reference_only"] = "reference_only"
