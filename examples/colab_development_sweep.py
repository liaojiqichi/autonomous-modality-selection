"""Reuse an initialized notebook; no model loading, downloads or selector calls."""

from __future__ import annotations

import importlib.metadata
import inspect
import json
import platform
from pathlib import Path
from typing import Any, Literal

from autonomous_modality.development_sweep import (
    SweepAttempt,
    SweepPlan,
    SweepScenario,
    file_sha256,
    planned_combinations,
    run_sweep,
)
from autonomous_modality.models import (
    CraterQuestion,
    CraterReference,
    DataAssetProfile,
    InputSelectionConstraints,
    InputSelectionRequest,
)


def snapshot(namespace: dict[str, Any]) -> dict[str, Any]:
    """Capture actual live functions/globals rather than relying on a stale CONFIG alone."""
    versions = {}
    for name in ("torch", "transformers", "bitsandbytes", "accelerate", "pydantic"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return json.loads(
        json.dumps(
            {
                "answer_function": inspect.getsource(namespace["answer_question"]),
                "generate_function": inspect.getsource(namespace["generate_reply"]),
                "build_messages_function": inspect.getsource(namespace["build_answer_messages"]),
                "config": namespace["CONFIG"],
                "runtime_answer_tokens": namespace["ANSWER_TOKENS"],
                "runtime_answer_policy": namespace["ANSWER_POLICY"],
                "catalogue_text": namespace["CATALOGUE_TEXT"],
                "terrain_text": namespace["TERRAIN_TEXT"],
                "preview_paths": {k: str(v) for k, v in namespace["PREVIEWS"].items()},
                "case_name": namespace["CASE_NAME"],
                "model_config": namespace["model"].config.to_dict(),
                "generation_config": namespace["model"].generation_config.to_dict(),
                "processor_class": type(namespace["processor"]).__name__,
                "python": platform.python_version(),
                "package_versions": versions,
                "model_device": str(getattr(namespace["model"], "device", "unavailable")),
                "model_dtype": str(getattr(namespace["model"], "dtype", "unavailable")),
            },
            default=str,
        )
    )


def prepare_from_notebook(
    namespace: dict[str, Any],
    include_references: bool = True,
    execution_kind: Literal["model", "test"] = "model",
) -> SweepPlan:
    """Prepare all combinations without generation; reuse verified existing files."""
    required = [
        "CONFIG",
        "QUESTIONS",
        "ASSETS",
        "CASE_ID",
        "CASE_NAME",
        "catalogue",
        "SOURCES",
        "PREVIEWS",
        "VIEW_DIR",
        "receipt_path",
        "GENERATION_LOG",
        "answer_question",
        "build_answer_messages",
        "generate_reply",
        "model",
        "processor",
        "ANSWER_TOKENS",
        "ANSWER_POLICY",
        "BUDGET",
        "MAX_MODALITIES",
        "CATALOGUE_TEXT",
        "TERRAIN_TEXT",
    ]
    absent = [name for name in required if name not in namespace]
    if absent:
        raise ValueError(f"Run notebook setup/generation/routing cells first. Missing: {absent}")
    if namespace["CONFIG"].get("split") != "development":
        raise ValueError("This diagnostic accepts development data only")
    if namespace["CONFIG"].get("cost_unit") != "legacy_ordinal_units":
        raise ValueError("This adapter expects the explicitly ordinal development protocol")
    receipt = json.loads(Path(namespace["receipt_path"]).read_text(encoding="utf-8"))
    expected_outputs = {
        "optical_local.png",
        "optical_context.png",
        "elevation.png",
        "profile_east.png",
        "profile_north.png",
        "terrain.txt",
    }
    if set(receipt["output_sha256"]) != expected_outputs:
        raise ValueError("Receipt must pin exactly the six expected evidence views")
    if set(namespace["PREVIEWS"]) != {Path(n).stem for n in expected_outputs if n.endswith(".png")}:
        raise ValueError("Exactly five named previews are required")
    paths = {str(Path(p).resolve()): file_sha256(Path(p)) for p in namespace["SOURCES"].values()}
    for name, expected in receipt["source_sha256"].items():
        if file_sha256(Path(namespace["SOURCES"][name])) != expected:
            raise ValueError(f"Scientific source changed: {name}")
    for name, expected in receipt["output_sha256"].items():
        path = Path(namespace["VIEW_DIR"]) / name
        if file_sha256(path) != expected:
            raise ValueError(f"Evidence view changed: {name}")
        paths[str(path.resolve())] = expected
    paths[str(Path(namespace["receipt_path"]).resolve())] = file_sha256(
        Path(namespace["receipt_path"])
    )
    for name, path in namespace["PREVIEWS"].items():
        if Path(path).resolve() != (Path(namespace["VIEW_DIR"]) / f"{name}.png").resolve():
            raise ValueError("Preview routing differs from receipt directory")
    if namespace["TERRAIN_TEXT"] != (Path(namespace["VIEW_DIR"]) / "terrain.txt").read_text(
        encoding="utf-8"
    ):
        raise ValueError("In-memory terrain summary changed")
    actual_catalogue = type(namespace["catalogue"]).model_validate_json(
        Path(namespace["SOURCES"]["catalogue.json"]).read_text(encoding="utf-8")
    )
    if json.loads(namespace["CATALOGUE_TEXT"]) != actual_catalogue.model_dump(mode="json"):
        raise ValueError("In-memory catalogue differs from verified source")
    scenarios = []
    for question in namespace["QUESTIONS"]:
        request = InputSelectionRequest(
            question=CraterQuestion(
                question_id=f"{namespace['CASE_ID']}-{question['question_id']}",
                text=question["text"].replace("{crater}", namespace["CASE_NAME"]),
                question_type=question["question_type"],
                crater=CraterReference(
                    crater_id=str(namespace["CASE_ID"]),
                    name=namespace["CASE_NAME"],
                    latitude=namespace["catalogue"].lat_n,
                    longitude=namespace["catalogue"].lon_e_0,
                ),
            ),
            assets=[
                DataAssetProfile(
                    asset_id=name,
                    modality=name,
                    title=name,
                    estimated_cost=item["cost"],
                    content_inventory=item.get("content_inventory"),
                )
                for name, item in sorted(namespace["ASSETS"].items())
            ],
            constraints=InputSelectionConstraints(
                maximum_modalities=namespace["MAX_MODALITIES"],
                maximum_total_cost=namespace["BUDGET"],
            ),
        )
        scenarios.append(
            SweepScenario(request=request, answer_requirements=question["answer_requirements"])
        )
    plan = SweepPlan(
        execution_kind=execution_kind,
        model_id=namespace["CONFIG"]["model"],
        scenarios=scenarios,
        include_references=include_references,
        generation_snapshot=snapshot(namespace),
        evidence_files=paths,
    )
    print(
        "Prepared; no inference yet. Answer calls:",
        sum(len(planned_combinations(s, include_references)) for s in scenarios),
    )
    return plan


def run_from_notebook(
    namespace: dict[str, Any],
    output: Path,
    include_references: bool = True,
    execution_kind: Literal["model", "test"] = "model",
) -> list[SweepAttempt]:
    """Explicit Colab inference; keep the notebook's answer signature and all old runs."""
    plan = prepare_from_notebook(namespace, include_references, execution_kind)

    def guarded_answer(question: str, requirements: list[str], selected: list[str]) -> str:
        if snapshot(namespace) != plan.generation_snapshot:
            raise ValueError("Live model/function/configuration changed during sweep")
        return namespace["answer_question"](question, requirements, selected)

    return run_sweep(
        plan,
        output,
        guarded_answer,
        namespace["build_answer_messages"],
        namespace["GENERATION_LOG"],
    )
