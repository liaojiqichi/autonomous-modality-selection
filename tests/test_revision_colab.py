"""Saved-draft provenance and formal notebook checks using invented fixtures."""

import ast
import copy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from autonomous_modality.answer_revision import RevisionPolicy
from autonomous_modality.modality_descriptions import ASSET_DESCRIPTION_VERSION, describe_assets
from autonomous_modality.revision_colab import (
    MATCHED_CONFIG,
    canonical_messages,
    digest_bytes,
    read_baseline,
    run_target_revisions,
    validate_baseline,
    validate_deployment,
)

ROOT = Path(__file__).resolve().parents[1]


def fixture_function(*args: object) -> None:
    """A recorded fake function, not a real inference interface."""


def fixture_messages(question: str, requirements: list[str], selected: list[str]) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": "/current/optical_local.png"},
                {"type": "text", "text": question + str(requirements) + str(selected)},
            ],
        }
    ]


@pytest.fixture
def baseline() -> tuple[bytes, bytes, dict, dict]:
    spec = {"question_id": "Q1", "text": "Test {crater}", "answer_requirements": ["Check"]}
    cfg = dict.fromkeys(MATCHED_CONFIG, "same fixture value")
    cfg["answer_tokens"] = 1024
    cfg["assets"] = describe_assets({"OPTICAL_IMAGE": {"cost": 2}})
    cfg["inventory_version"] = ASSET_DESCRIPTION_VERSION
    cfg["asset_description_version"] = ASSET_DESCRIPTION_VERSION
    cfg["asset_description_scope"] = "all_selectors"
    ns = {
        "CONFIG": cfg,
        "MODEL_NAME": "fixture",
        "CASE_ID": "1",
        "CASE_NAME": "Example",
        "ASSETS": copy.deepcopy(cfg["assets"]),
        "valid_selection": sorted,
        "generate_reply": fixture_function,
        "build_answer_messages": fixture_messages,
        "answer_question": fixture_function,
        "select_inputs": fixture_function,
        "REVISION_RUNTIME": {
            "environment": {"torch": "1", "transformers": "1", "bitsandbytes": "1", "Pillow": "1"},
            "image_processor": {"fake": 1},
            "chat_template": "fixture",
            "tokenizer_chat_template": None,
            "model_revision": "a" * 40,
            "processor_revision": "b" * 40,
        },
    }
    metadata = {
        "config": cfg,
        **ns["REVISION_RUNTIME"],
        "functions": {
            n: inspect.getsource(ns[n])
            for n in ("generate_reply", "build_answer_messages", "answer_question", "select_inputs")
        },
    }
    meta = json.dumps(metadata).encode()
    generation = {
        "messages": fixture_messages("Test Example", ["Check"], ["OPTICAL_IMAGE"]),
        "max_new_tokens": 1024,
        "finish_reason": "eos",
        "text": "Fixture answer",
    }
    record = {
        "record_version": "colab-ap-heldout-four-modality-1",
        "run_sha256": digest_bytes(meta),
        "model": "fixture",
        "case_id": "1",
        "question_id": "Q1",
        "question": "Test Example",
        "condition": "AGENT",
        "draw_index": 0,
        "status": "success",
        "selected": ["OPTICAL_IMAGE"],
        "selection_rationale": "Test",
        "input_cost": 2,
        "elapsed_seconds": 1.0,
        "selection_seconds": 0.5,
        "answer_seconds": 0.5,
        "selection_generations": [generation],
        "answer_generations": [generation],
        "answer": "Fixture answer",
        "finish_reason": "eos",
    }
    return json.dumps(record).encode(), meta, ns, spec


def test_valid_baseline(baseline: tuple) -> None:
    raw, meta, ns, spec = baseline
    assert validate_baseline(raw, meta, ns, spec).answer == "Fixture answer"


@pytest.mark.parametrize("field", MATCHED_CONFIG)
def test_every_configuration_drift_rejected(baseline: tuple, field: str) -> None:
    raw, meta, ns, spec = baseline
    ns["CONFIG"][field] = "different"
    with pytest.raises(ValueError, match="BASELINE_CONFIG_MISMATCH"):
        validate_baseline(raw, meta, ns, spec)


@pytest.mark.parametrize(
    "field", ["environment", "image_processor", "chat_template", "tokenizer_chat_template"]
)
def test_runtime_drift_rejected(baseline: tuple, field: str) -> None:
    raw, meta, ns, spec = baseline
    ns["REVISION_RUNTIME"][field] = "different"
    with pytest.raises(ValueError, match="BASELINE_RUNTIME_MISMATCH"):
        validate_baseline(raw, meta, ns, spec)


@pytest.mark.parametrize(
    "field,value",
    [
        ("question", "Other question"),
        ("case_id", "2"),
        ("model", "different"),
        ("answer", "Changed answer"),
        ("input_cost", 4),
        ("run_sha256", "f" * 64),
        ("finish_reason", "length"),
    ],
)
def test_record_tampering_rejected(baseline: tuple, field: str, value: object) -> None:
    raw, meta, ns, spec = baseline
    data = json.loads(raw)
    data[field] = value
    with pytest.raises(ValueError):
        validate_baseline(json.dumps(data).encode(), meta, ns, spec)


def test_failed_baseline_retained(baseline: tuple) -> None:
    raw, meta, ns, spec = baseline
    data = json.loads(raw)
    data["status"] = "error"
    assert validate_baseline(json.dumps(data).encode(), meta, ns, spec).status == "error"


def test_message_paths_relocate_only() -> None:
    old = fixture_messages("Question", [], [])
    new = copy.deepcopy(old)
    old[0]["content"][0]["image"] = r"D:\old\optical_local.png"
    assert canonical_messages(old) == canonical_messages(new)
    new[0]["content"][1]["text"] = "Changed data"
    assert canonical_messages(old) != canonical_messages(new)


def test_baseline_directory(baseline: tuple, tmp_path: Path) -> None:
    raw, meta, _, _ = baseline
    suffix = "fixture/crater-1/budget-4/Q1__AGENT__r01.json"
    folder = tmp_path / "run" / Path(suffix).parent
    folder.mkdir(parents=True)
    (folder / Path(suffix).name).write_bytes(raw)
    (folder / "run_metadata.json").write_bytes(meta)
    assert read_baseline(tmp_path / "run", suffix)[1:] == (raw, meta)
    with pytest.raises(ValueError, match="EXPECTED_ONE"):
        read_baseline(tmp_path / "run", suffix.replace("Q1", "Q2"))


def test_blocked_resume_and_interrupted_journal(baseline: tuple, tmp_path: Path) -> None:
    raw, meta, ns, spec = baseline
    deployment = fixture_deployment(ns)
    metadata = json.loads(meta)
    metadata["config"]["runtime_approval_sha256"] = digest_bytes(deployment)
    meta = json.dumps(metadata).encode()
    data = json.loads(raw)
    data["run_sha256"] = digest_bytes(meta)
    data["status"] = "error"
    folder = tmp_path / "source/fixture/crater-1/budget-4"
    folder.mkdir(parents=True)
    (folder / "Q1__AGENT__r01.json").write_text(json.dumps(data))
    (folder / "run_metadata.json").write_bytes(meta)
    (folder.parent.parent / "deployment-lock-b4.json").write_bytes(deployment)
    ns.update(
        QUESTIONS=[spec],
        MODEL_TAG="fixture",
        BUDGET=4,
        REVISION_APPROVAL={},
        GENERATION_LOG=[],
        gc=SimpleNamespace(collect=lambda: None),
        torch=SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: None)),
    )
    destination = tmp_path / "results"
    records = run_target_revisions(ns, tmp_path / "source", destination, RevisionPolicy())
    saved_metadata = json.loads((destination / "revision_metadata.json").read_text())
    assert saved_metadata["reviewer_prompt_version"] == "answer-revision-evidence-retention-1.1"
    assert "reviewer_asset_amendment" not in saved_metadata
    descriptions = saved_metadata["asset_descriptions"]
    assert descriptions["scope"] == "all_selectors"
    assert descriptions["assets"] == saved_metadata["base_config"]["assets"]
    assert len(descriptions["implementation_sha256"]) == 64
    assert "Supported analyses:" in descriptions["assets"]["OPTICAL_IMAGE"]["description"]
    assert records[0].status == "blocked"
    assert records[0].generation_log == []
    assert run_target_revisions(ns, tmp_path / "source", destination, RevisionPolicy()) == records
    other = tmp_path / "interrupted"
    other.mkdir()
    (other / "Q1__AGENT_ANSWER_REVISION__r01.started.json").write_text("{}")
    with pytest.raises(FileExistsError):
        run_target_revisions(ns, tmp_path / "source", other, RevisionPolicy())


def test_notebook_preserves_inference_and_compiles() -> None:
    base = json.loads((ROOT / "notebooks/autonomous_modality_selection_heldout.ipynb").read_text())
    target = ROOT / "notebooks" / "autonomous_modality_selection_answer_revision_formal.ipynb"
    n = json.loads(target.read_text(encoding="utf-8"))
    sources = ["".join(c["source"]) for c in n["cells"]]
    for cell in n["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            compile("".join(cell["source"]), str(target), "exec")
    for index in (8, 11, 12, 13, 14):
        expected = ast.dump(ast.parse("".join(base["cells"][index]["source"])))
        assert any(
            ast.dump(ast.parse(s)) == expected
            for c, s in zip(n["cells"], sources, strict=True)
            if c["cell_type"] == "code"
        )
    full = "\n".join(sources)
    assert "HISTORICAL_SOURCE" not in full
    assert "source = RESULTS_ROOT / RUN_LABEL" in full
    assert "REVISION_CUMULATIVE_BUDGET = 7" in full
    assert 'MODE = "prepare"' not in full
    assert "DEV_RESULTS_ZIP" not in full
    assert "CONFIRM_DEVELOPMENT_REVIEW" not in full
    assert "load_approval(" not in full
    assert "RuntimeDeclaration(" in full
    assert '"runtime_declaration_sha256": sha256(DEPLOYMENT_PATH)' in full
    assert "Qwen/Qwen3-VL-8B-Instruct" in full
    assert "google/gemma-4-E4B-it" in full


def fixture_deployment(namespace: dict) -> bytes:
    runtime = namespace["REVISION_RUNTIME"]
    return json.dumps(
        {
            "version": "heldout-runtime-approval-1",
            "approved_by": "Fixture",
            "protocol_sha256": "c" * 64,
            "notebook_sha256": "d" * 64,
            "models": {
                "fixture": {
                    "model_revision": runtime["model_revision"],
                    "processor_revision": runtime["processor_revision"],
                    "environment": runtime["environment"],
                    "image_processor_size": {},
                    "image_processor_config": runtime["image_processor"],
                    "validation_file": "fixture.json",
                    "validation_sha256": "e" * 64,
                    "validation_split": "development",
                    "reviewed_pass": True,
                    "validation_notes": "Invented fixture validation only.",
                }
            },
        }
    ).encode()


def test_deployment_revision_checked_with_null_config(baseline: tuple) -> None:
    _, meta, ns, _ = baseline
    raw = fixture_deployment(ns)
    metadata = json.loads(meta)
    metadata["config"]["model_revision"] = None
    metadata["config"]["runtime_approval_sha256"] = digest_bytes(raw)
    encoded = json.dumps(metadata).encode()
    validate_deployment(raw, encoded, "fixture", ns["REVISION_RUNTIME"])
    ns["REVISION_RUNTIME"]["model_revision"] = "f" * 40
    with pytest.raises(ValueError, match="DEPLOYMENT_MISMATCH"):
        validate_deployment(raw, encoded, "fixture", ns["REVISION_RUNTIME"])


@pytest.mark.parametrize("changed", [None, "hash", "revision", "status"])
def test_direct_runtime_declaration(baseline: tuple, changed: str | None) -> None:
    from autonomous_modality.revision_colab import RuntimeDeclaration, RuntimeDeployment

    _, meta, ns, _ = baseline
    runtime = ns["REVISION_RUNTIME"]
    declaration = RuntimeDeclaration(
        protocol_sha256="a" * 64,
        notebook_sha256="b" * 64,
        models={
            "fixture": RuntimeDeployment(
                model_revision=runtime["model_revision"],
                processor_revision=runtime["processor_revision"],
                environment=runtime["environment"],
                image_processor_config=runtime["image_processor"],
            )
        },
        python_version="3.12",
        gpu="Fixture",
        cuda="13.0",
    ).model_dump(mode="json")
    if changed == "status":
        declaration["validation_status"] = "passed"
    raw = json.dumps(declaration).encode()
    metadata = json.loads(meta)
    metadata["config"]["runtime_declaration_sha256"] = (
        "c" * 64 if changed == "hash" else digest_bytes(raw)
    )
    if changed == "revision":
        runtime["model_revision"] = "f" * 40
    if changed:
        with pytest.raises(ValueError):
            validate_deployment(raw, json.dumps(metadata).encode(), "fixture", runtime)
    else:
        validate_deployment(raw, json.dumps(metadata).encode(), "fixture", runtime)
