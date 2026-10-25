"""Colab bridge for the formal answer-informed revision condition."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import time
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import Field

from autonomous_modality.answer_revision import (
    PROMPT,
    InitialAnswer,
    RevisionPolicy,
    RevisionResult,
    run_answer_revision,
)
from autonomous_modality.heldout_colab import RuntimeApproval, preserve_json
from autonomous_modality.iterative import GenerationReply
from autonomous_modality.iterative_colab import notebook_generator
from autonomous_modality.models import (
    CraterQuestion,
    DataAssetProfile,
    InputSelectionConstraints,
    InputSelectionRequest,
    StrictModel,
)


class SavedGeneration(StrictModel):
    messages: list[dict[str, Any]]
    max_new_tokens: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: Literal["error", "eos", "length", "unknown"] = "error"
    elapsed_seconds: float = 0.0
    peak_gpu_gib: float | None = None
    text: str | None = None
    error: str | None = None


class RuntimeDeployment(StrictModel):
    """Actual execution settings; this record does not imply a validation run."""

    model_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    processor_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    environment: dict[str, str] = Field(min_length=4)
    image_processor_config: dict[str, Any]


class RuntimeDeclaration(StrictModel):
    version: Literal["formal-runtime-declaration-1"] = "formal-runtime-declaration-1"
    validation_status: Literal["not_performed_by_this_notebook"] = "not_performed_by_this_notebook"
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    notebook_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    models: dict[str, RuntimeDeployment] = Field(min_length=1, max_length=1)
    python_version: str
    gpu: str
    cuda: str


class BaselineRecord(StrictModel):
    """Exact schema of existing formal one-shot records, including failed attempts."""

    record_version: Literal["colab-ap-heldout-four-modality-1"]
    run_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model: str
    case_id: str
    question_id: str
    question: str
    condition: Literal["AGENT"]
    draw_index: Literal[0]
    selection_seed: None = None
    status: Literal["success", "truncated", "incomplete", "error"]
    selected: list[str]
    selection_rationale: str
    iterative_selection: None = None
    input_cost: int
    elapsed_seconds: float
    selection_seconds: float
    answer_seconds: float
    peak_gpu_gib: float | None = None
    selection_generations: list[SavedGeneration]
    answer_generations: list[SavedGeneration]
    answer: str | None = None
    finish_reason: Literal["eos", "length", "unknown"] | None = None
    error_stage: Literal["selection", "answer"] | None = None
    error_type: str | None = None
    error: str | None = None
    traceback: str | None = None


class RevisionAttempt(StrictModel):
    version: Literal["answer-revision-colab-1"] = "answer-revision-colab-1"
    condition: Literal["AGENT_ANSWER_REVISION"] = "AGENT_ANSWER_REVISION"
    model: str
    case_id: str
    question_id: str
    run_sha256: str
    source_record_sha256: str
    source_metadata_sha256: str
    status: Literal["success", "truncated", "incomplete", "error", "blocked"]
    result: RevisionResult | None = None
    error: str | None = None
    elapsed_seconds: float
    generation_log: list[SavedGeneration]
    # Baseline calls are a shared dependency, recorded separately from revision calls.
    initial_generation_log: list[SavedGeneration]


def digest_bytes(value: bytes) -> str:
    """Hash exact file bytes."""
    return hashlib.sha256(value).hexdigest()


def canonical_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Relocate image paths only; input byte identity is checked separately."""
    result = copy.deepcopy(messages)
    for message in result:
        for block in message["content"]:
            if block.get("type") == "image":
                block["image"] = PureWindowsPath(block["image"]).name
    return result


def read_baseline(source: Path, suffix: str) -> tuple[str, bytes, bytes]:
    """Read a uniquely identified saved AGENT record and its metadata."""
    if not source.is_dir():
        raise FileNotFoundError(f"Baseline run folder not found: {source}")
    matches = [
        p for p in source.rglob(PurePosixPath(suffix).name) if p.as_posix().endswith("/" + suffix)
    ]
    if len(matches) != 1:
        raise ValueError(f"EXPECTED_ONE_BASELINE: {suffix}, found {len(matches)}")
    path = matches[0]
    return str(path), path.read_bytes(), path.with_name("run_metadata.json").read_bytes()


def read_deployment(source: Path, model_tag: str, budget: int) -> bytes:
    """Read the archived deployment lock, which records immutable model/processor revisions."""
    suffix = f"{model_tag}/deployment-lock-b{budget}.json"
    names = [
        p
        for p in source.rglob(f"deployment-lock-b{budget}.json")
        if p.as_posix().endswith("/" + suffix)
    ]
    if len(names) != 1:
        raise ValueError("EXPECTED_ONE_DEPLOYMENT_LOCK")
    return names[0].read_bytes()


def validate_deployment(raw: bytes, metadata: bytes, model: str, runtime: dict) -> None:
    """Check revision provenance even when model.config._commit_hash was null."""
    version = json.loads(raw).get("version")
    declaration = (
        RuntimeDeclaration.model_validate_json(raw)
        if version == "formal-runtime-declaration-1"
        else RuntimeApproval.model_validate_json(raw)
    )
    config = json.loads(metadata)["config"]
    key = (
        "runtime_declaration_sha256"
        if version == "formal-runtime-declaration-1"
        else ("runtime_approval_sha256")
    )
    if config[key] != digest_bytes(raw):
        raise ValueError("BASELINE_DEPLOYMENT_HASH_MISMATCH")
    if model not in declaration.models:
        raise ValueError("BASELINE_DEPLOYMENT_MODEL_MISSING")
    deployment = declaration.models[model]
    if (
        deployment.model_revision != runtime["model_revision"]
        or deployment.processor_revision != runtime["processor_revision"]
        or deployment.environment != runtime["environment"]
        or deployment.image_processor_config != runtime["image_processor"]
    ):
        raise ValueError("BASELINE_DEPLOYMENT_MISMATCH")


# These describe the scientific task and answer process. Provenance fields that must
# differ for an additive extension (commit, notebook and approval hashes) are retained
# in both records instead of being falsely treated as equal.
MATCHED_CONFIG = (
    "model",
    "attention_policy",
    "model_revision",
    "four_bit",
    "seed",
    "budget",
    "maximum_modalities",
    "random_draws",
    "image_edge",
    "answer_tokens",
    "answer_repetition_penalty",
    "dataset_release_sha256",
    "formal_protocol_sha256",
    "runtime_amendment_sha256",
    "selector_tokens",
    "max_input_tokens",
    "decoding",
    "thinking",
    "language",
    "answer_policy_version",
    "inventory_version",
    "cost_unit",
    "question_sha256",
    "source_sha256",
    "view_receipt",
    "selector_task",
    "answer_policy",
    "assets",
)


def validate_baseline(
    raw: bytes,
    metadata_raw: bytes,
    namespace: Mapping[str, Any],
    spec: dict[str, Any],
) -> BaselineRecord:
    """Reject identity, evidence, environment, prompt or generation-interface drift."""
    record = BaselineRecord.model_validate_json(raw)
    if record.run_sha256 != digest_bytes(metadata_raw):
        raise ValueError("BASELINE_METADATA_HASH_MISMATCH")
    metadata = json.loads(metadata_raw)
    expected = namespace["CONFIG"]
    for key in MATCHED_CONFIG:
        if key not in metadata["config"] or metadata["config"][key] != expected[key]:
            raise ValueError(f"BASELINE_CONFIG_MISMATCH: {key}")
    for key in ("environment", "image_processor", "chat_template", "tokenizer_chat_template"):
        if key not in metadata or metadata[key] != namespace["REVISION_RUNTIME"][key]:
            raise ValueError(f"BASELINE_RUNTIME_MISMATCH: {key}")
    for name in ("generate_reply", "build_answer_messages", "answer_question", "select_inputs"):
        old = ast.dump(ast.parse(metadata["functions"][name]), include_attributes=False)
        new = ast.dump(ast.parse(inspect.getsource(namespace[name])), include_attributes=False)
        if old != new:
            raise ValueError(f"BASELINE_FUNCTION_MISMATCH: {name}")
    question = spec["text"].replace("{crater}", namespace["CASE_NAME"])
    if (record.model, record.case_id, record.question_id, record.question) != (
        namespace["MODEL_NAME"],
        namespace["CASE_ID"],
        spec["question_id"],
        question,
    ):
        raise ValueError("BASELINE_IDENTITY_MISMATCH")
    if record.status != "success":
        return record  # Preserve as a blocked dependency; never regenerate it silently.
    if (
        record.finish_reason != "eos"
        or not record.answer
        or record.error
        or len(record.answer_generations) != 1
        or not record.selection_generations
    ):
        raise ValueError("BASELINE_NOT_A_COMPLETE_LOGGED_ANSWER")
    for generation in record.selection_generations + record.answer_generations:
        if generation.finish_reason != "eos" or generation.error is not None:
            raise ValueError("BASELINE_GENERATION_FAILED")
    generation = record.answer_generations[0]
    if generation.text != record.answer or generation.max_new_tokens != expected["answer_tokens"]:
        raise ValueError("BASELINE_ANSWER_LOG_MISMATCH")
    if record.selected != namespace["valid_selection"](record.selected):
        raise ValueError("BASELINE_SELECTION_INVALID")
    if record.input_cost != sum(namespace["ASSETS"][m]["cost"] for m in record.selected):
        raise ValueError("BASELINE_COST_MISMATCH")
    current_messages = namespace["build_answer_messages"](
        question, spec["answer_requirements"], record.selected
    )
    if canonical_messages(generation.messages) != canonical_messages(current_messages):
        raise ValueError("BASELINE_ACTUAL_ANSWER_INPUT_MISMATCH")
    return record


def build_revision_request(
    namespace: Mapping[str, Any], spec: dict[str, Any]
) -> InputSelectionRequest:
    """Use the same question, asset declarations and final-set constraints as AGENT."""
    return InputSelectionRequest(
        question=CraterQuestion(
            question_id=f"{namespace['CASE_ID']}-{spec['question_id']}",
            text=spec["text"].replace("{crater}", namespace["CASE_NAME"]),
            question_type=spec["question_type"],
            answer_requirements=spec["answer_requirements"],
        ),
        assets=[
            DataAssetProfile(
                asset_id=name,
                modality=name,
                title=name,
                estimated_cost=asset["cost"],
                limitations=[asset["description"]],
                content_inventory=asset["content_inventory"],
            )
            for name, asset in sorted(namespace["ASSETS"].items())
        ],
        constraints=InputSelectionConstraints(
            maximum_modalities=namespace["MAX_MODALITIES"],
            maximum_total_cost=namespace["BUDGET"],
        ),
    )


def execute_revision(
    namespace: Mapping[str, Any],
    spec: dict[str, Any],
    initial: InitialAnswer,
    policy: RevisionPolicy,
) -> RevisionResult:
    """Pass initial evidence to the reviewer and only the replacement evidence to the answer."""
    request = build_revision_request(namespace, spec)
    log = namespace["GENERATION_LOG"]
    generator = notebook_generator(namespace["generate_reply"], log)

    def fresh_answer(selected: list[str]) -> GenerationReply:
        # Recheck frozen bytes before loading any replacement evidence.
        for name in selected:
            namespace["load_notebook_evidence"](namespace["InputDataModality"](name))
        before = len(log)
        text = namespace["answer_question"](
            request.question.text, spec["answer_requirements"], selected
        )
        if len(log) != before + 1 or log[-1]["text"] != text:
            raise ValueError("REVISED_ANSWER_NOT_LOGGED_EXACTLY_ONCE")
        entry = log[-1]
        return GenerationReply(
            **{
                k: entry[k]
                for k in ("text", "finish_reason", "input_tokens", "output_tokens", "peak_gpu_gib")
            }
        )

    for name in initial.selected:
        namespace["load_notebook_evidence"](namespace["InputDataModality"](name))
    return run_answer_revision(
        request,
        initial,
        policy,
        namespace["build_evidence_content"](initial.selected),
        generator,
        fresh_answer,
        execution_kind="model",
    )


def run_target_revisions(
    namespace: Mapping[str, Any],
    source: Path,
    destination: Path,
    policy: RevisionPolicy,
) -> list[RevisionAttempt]:
    """Validate baseline records before inference; save once and resume safely."""
    deployment = read_deployment(source, namespace["MODEL_TAG"], namespace["BUDGET"])
    validated = []
    for spec in namespace["QUESTIONS"]:
        suffix = (
            f"{namespace['MODEL_TAG']}/crater-{namespace['CASE_ID']}/"
            f"budget-{namespace['BUDGET']}/{spec['question_id']}__AGENT__r01.json"
        )
        path, raw, metadata = read_baseline(source, suffix)
        validate_deployment(
            deployment, metadata, namespace["MODEL_NAME"], namespace["REVISION_RUNTIME"]
        )
        record = validate_baseline(raw, metadata, namespace, spec)
        validated.append((spec, path, raw, metadata, record))
    destination.mkdir(parents=True, exist_ok=True)
    config = {
        "version": policy.version,
        "policy": policy.model_dump(mode="json"),
        "prompt": PROMPT,
        "base_config": namespace["CONFIG"],
        "runtime": namespace["REVISION_RUNTIME"],
        "revision_configuration": (
            namespace["REVISION_PROTOCOL"]
            if "REVISION_PROTOCOL" in namespace
            else namespace["REVISION_APPROVAL"]
        ),
        "baseline_deployment": json.loads(deployment),
        "sources": {
            s[0]["question_id"]: {
                "record_sha256": digest_bytes(s[2]),
                "metadata_sha256": digest_bytes(s[3]),
            }
            for s in validated
        },
    }
    config_path = destination / "revision_metadata.json"
    preserve_json(config_path, config)
    run_hash = digest_bytes(config_path.read_bytes())
    attempts = []
    for spec, path, raw, metadata, record in validated:
        target = destination / f"{spec['question_id']}__AGENT_ANSWER_REVISION__r01.json"
        if target.exists():
            previous = RevisionAttempt.model_validate_json(target.read_bytes())
            if previous.run_sha256 != run_hash or previous.source_record_sha256 != digest_bytes(
                raw
            ):
                raise ValueError("EXISTING_REVISION_CHANGED")
            attempts.append(previous)
            print(spec["question_id"], "Retained", previous.status)
            continue
        # Exclusive intent journal prevents hidden retries after interruption/OOM/session loss.
        intent = target.with_suffix(".started.json")
        with intent.open("x", encoding="utf-8") as stream:
            json.dump({"run_sha256": run_hash, "source_record_sha256": digest_bytes(raw)}, stream)
        log = namespace["GENERATION_LOG"]
        log.clear()
        start = time.perf_counter()
        outcome = {"status": "blocked", "error": f"Initial AGENT status: {record.status}"}
        try:
            if record.status == "success":
                initial = InitialAnswer(
                    model=record.model,
                    case_id=record.case_id,
                    question_id=record.question_id,
                    question=record.question,
                    selected=record.selected,
                    answer=record.answer,
                    source_record_sha256=digest_bytes(raw),
                    source_metadata_sha256=digest_bytes(metadata),
                    source_path=path,
                )
                result = execute_revision(namespace, spec, initial, policy)
                outcome = {"status": result.status, "result": result, "error": result.error}
        except Exception as exc:
            outcome = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        attempt = RevisionAttempt(
            model=record.model,
            case_id=record.case_id,
            question_id=record.question_id,
            run_sha256=run_hash,
            source_record_sha256=digest_bytes(raw),
            source_metadata_sha256=digest_bytes(metadata),
            elapsed_seconds=time.perf_counter() - start,
            generation_log=copy.deepcopy(log),
            initial_generation_log=record.selection_generations + record.answer_generations,
            **outcome,
        )
        with target.open("x", encoding="utf-8") as stream:
            stream.write(attempt.model_dump_json(indent=2))
        attempts.append(attempt)
        print(
            spec["question_id"],
            attempt.status,
            attempt.result.action if attempt.result else attempt.error,
        )
        log.clear()
        namespace["gc"].collect()
        namespace["torch"].cuda.empty_cache()
    return attempts
