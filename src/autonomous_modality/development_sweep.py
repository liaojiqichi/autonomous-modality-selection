"""Opt-in exhaustive development runs using existing Colab answer interfaces.

This module never loads a model, downloads data, or changes historical records.
"""

from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Callable
from itertools import combinations
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, JsonValue, model_validator

from autonomous_modality.iterative import GenerationReply
from autonomous_modality.models import (
    AssetAvailability,
    InputDataModality,
    InputSelectionRequest,
    NonEmptyString,
    StrictModel,
)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Answer = Callable[[str, list[str], list[str]], str]
BuildMessages = Callable[[str, list[str], list[str]], list[dict[str, Any]]]


class Combination(StrictModel):
    """One feasible nonempty subset or explicitly separate reference control."""

    role: Literal["feasible", "no_data_reference", "all_available_reference"] = "feasible"
    selected: list[InputDataModality]
    total_cost: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        """Reject contradictory references and duplicate or unsorted modalities."""
        if self.selected != sorted(set(self.selected)):
            raise ValueError("selection must be unique and canonically ordered")
        if self.role == "no_data_reference":
            if self.selected or self.total_cost:
                raise ValueError("no-data reference must be empty and cost zero")
        elif not self.selected:
            raise ValueError("data combination must be nonempty")
        return self


def enumerate_combinations(request: InputSelectionRequest) -> list[Combination]:
    """Use RANDOM's nonempty feasible-set semantics, including hard constraints."""
    assets = sorted(
        (
            a
            for a in request.assets
            if a.availability == AssetAvailability.AVAILABLE
            and a.modality not in request.constraints.forbidden_modalities
        ),
        key=lambda a: a.modality.value,
    )
    c = request.constraints
    result = []
    for size in range(1, min(c.maximum_modalities, len(assets)) + 1):
        for group in combinations(assets, size):
            cost = sum(a.estimated_cost for a in group)
            if not c.required_modalities.issubset(a.modality for a in group):
                continue
            if c.maximum_total_cost is not None and cost > c.maximum_total_cost:
                continue
            result.append(Combination(selected=[a.modality.value for a in group], total_cost=cost))
    return result


class SweepScenario(StrictModel):
    """A development question and its original answer requirements."""

    request: InputSelectionRequest
    answer_requirements: list[NonEmptyString]


class SweepPlan(StrictModel):
    """Pinned configuration. Constructing a plan is not model inference."""

    model_config = ConfigDict(str_strip_whitespace=False)

    version: Literal["development-combination-sweep-1.0"] = "development-combination-sweep-1.0"
    split: Literal["development"] = "development"
    execution_kind: Literal["model", "test"]
    model_id: NonEmptyString
    cost_unit: Literal["legacy_ordinal_units"] = "legacy_ordinal_units"
    scenarios: list[SweepScenario] = Field(min_length=1)
    include_references: bool = True
    generation_snapshot: dict[str, JsonValue] = Field(min_length=1)
    evidence_files: dict[str, Digest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scenarios(self) -> Self:
        """Reject repeated questions and unusable or unpinned configurations."""
        ids = [s.request.question.question_id for s in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario question IDs must be unique")
        for s in self.scenarios:
            if not enumerate_combinations(s.request):
                raise ValueError("scenario has no feasible nonempty subset")
        for key in ("answer_function", "generate_function", "build_messages_function", "config"):
            if key not in self.generation_snapshot:
                raise ValueError(f"generation snapshot missing {key}")
        return self


class SweepAttempt(StrictModel):
    """Started/errors/truncations remain recorded and are never retried silently."""

    model_config = ConfigDict(str_strip_whitespace=False)

    version: Literal["development-sweep-attempt-1.0"] = "development-sweep-attempt-1.0"
    run_sha256: Digest
    task_id: Digest
    execution_kind: Literal["model", "test"]
    question_id: NonEmptyString
    combination: Combination
    status: Literal["started", "success", "truncated", "error"]
    messages: list[dict[str, JsonValue]] = Field(min_length=1)
    generation: GenerationReply | None = None
    raw_generation: dict[str, JsonValue] | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        """Require genuine logged EOS for success and preserve unfinished attempts."""
        if self.status in {"success", "truncated"}:
            if self.generation is None or not self.generation.text.strip():
                raise ValueError("completed attempt requires a nonempty generation")
            expected = "success" if self.generation.finish_reason == "eos" else "truncated"
            if expected != self.status or self.error is not None:
                raise ValueError("inconsistent completion status")
        if self.status == "error" and not self.error:
            raise ValueError("error attempt needs a diagnostic")
        if self.status == "started" and any(
            x is not None for x in (self.generation, self.raw_generation, self.error)
        ):
            raise ValueError("started attempt cannot contain a completed result")
        return self


def file_sha256(path: Path) -> str:
    """Hash an existing file without changing it."""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _verify_evidence(plan: SweepPlan) -> None:
    for name, expected in plan.evidence_files.items():
        if file_sha256(Path(name)) != expected:
            raise ValueError(f"Evidence changed: {name}")


def planned_combinations(scenario: SweepScenario, references: bool) -> list[Combination]:
    """Keep budget-unmatched all-data and intentional empty input outside the search."""
    rows = enumerate_combinations(scenario.request)
    if references:
        assets = sorted(
            (
                a
                for a in scenario.request.assets
                if a.availability == AssetAvailability.AVAILABLE
                and a.modality not in scenario.request.constraints.forbidden_modalities
            ),
            key=lambda a: a.modality.value,
        )
        rows += [
            Combination(role="no_data_reference", selected=[], total_cost=0),
            Combination(
                role="all_available_reference",
                selected=[a.modality.value for a in assets],
                total_cost=sum(a.estimated_cost for a in assets),
            ),
        ]
    return rows


def run_sweep(
    plan: SweepPlan,
    output: Path,
    answer_question: Answer,
    build_messages: BuildMessages,
    generation_log: list[dict[str, Any]],
) -> list[SweepAttempt]:
    """Call existing notebook functions; freeze identity and skip every existing attempt.

    Call only in Colab for execution_kind=model. Fixtures must use test. No selector
    rationales or condition labels enter the answer callback. Do not edit callbacks,
    model state or global configuration during a run. Restart under a new output
    directory after any such change. Interruptions keep a started record for audit.
    """
    plan = SweepPlan.model_validate_json(plan.model_dump_json())
    _verify_evidence(plan)
    payload = {"plan": plan.model_dump(mode="json"), "runner_sha256": file_sha256(Path(__file__))}
    encoded = _bytes(payload)
    run_hash = hashlib.sha256(encoded).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "sweep_plan.json"
    if manifest.exists():
        if manifest.read_bytes() != encoded:
            raise ValueError("Sweep configuration changed; use a new output directory")
    else:
        if any(output.iterdir()):
            raise ValueError("New sweep directory must be empty")
        with manifest.open("xb") as stream:
            stream.write(encoded)
    records = []
    for scenario in plan.scenarios:
        q = scenario.request.question
        for combo in planned_combinations(scenario, plan.include_references):
            identity = [q.question_id, combo.model_dump(mode="json")]
            task_id = hashlib.sha256(_bytes(identity)).hexdigest()
            destination = output / f"{task_id}.json"
            _verify_evidence(plan)
            messages = build_messages(q.text, scenario.answer_requirements, combo.selected)
            if destination.exists():
                existing = SweepAttempt.model_validate_json(destination.read_text(encoding="utf-8"))
                if (
                    existing.run_sha256 != run_hash
                    or existing.task_id != task_id
                    or existing.question_id != q.question_id
                    or existing.combination != combo
                    or existing.messages != messages
                    or existing.execution_kind != plan.execution_kind
                ):
                    raise ValueError("Existing attempt identity mismatch")
                records.append(existing)
                continue
            data = dict(
                run_sha256=run_hash,
                task_id=task_id,
                execution_kind=plan.execution_kind,
                question_id=q.question_id,
                combination=combo,
                status="started",
                messages=messages,
            )
            started = SweepAttempt(**data)
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(started.model_dump_json(indent=2))
            before = len(generation_log)
            try:
                answer = answer_question(q.text, scenario.answer_requirements, combo.selected)
                if len(generation_log) != before + 1:
                    raise ValueError("Expected exactly one fresh answer generation log")
                raw = generation_log[-1]
                if raw.get("messages") != messages or raw.get("text") != answer:
                    raise ValueError("Actual answer log differs from pinned messages or text")
                if raw.get("error"):
                    raise ValueError(f"Generator reported error: {raw['error']}")
                reply = GenerationReply(
                    text=answer,
                    finish_reason=raw.get("finish_reason", "unknown"),
                    input_tokens=raw.get("input_tokens"),
                    output_tokens=raw.get("output_tokens"),
                    peak_gpu_gib=raw.get("peak_gpu_gib"),
                )
                _verify_evidence(plan)
                data.update(
                    status="success" if reply.finish_reason == "eos" else "truncated",
                    generation=reply,
                    raw_generation=raw,
                )
                final = SweepAttempt(**data)
            except Exception:
                data.update(status="error", error=traceback.format_exc())
                if len(generation_log) == before + 1:
                    data["raw_generation"] = generation_log[-1]
                final = SweepAttempt(**data)
            temporary = destination.with_suffix(".json.tmp")
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(final.model_dump_json(indent=2))
            temporary.replace(destination)
            records.append(final)
            print(q.question_id, combo.role, combo.selected, final.status, flush=True)
    return records
