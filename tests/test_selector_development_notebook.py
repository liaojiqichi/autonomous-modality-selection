"""Offline contract tests for the isolated three-target development notebook."""

from __future__ import annotations

import ast
import copy
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / "scripts/build_selector_development_notebook.py"))
NOTEBOOK = ROOT / BUILDER["DESTINATION"]


def sources() -> list[str]:
    """Read code cells without invoking any notebook code."""
    return [
        "".join(c["source"])
        for c in json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
        if c["cell_type"] == "code"
    ]


def blocks() -> dict[str, str]:
    """Read embedded sources through literal evaluation only."""
    source = next(s for s in sources() if s.startswith("EXECUTION_SOURCES ="))
    return ast.literal_eval(ast.parse(source).body[0].value)


def test_generated_notebook_clean_and_matches_builder() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook == BUILDER["build_notebook"]()
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None and cell["outputs"] == []
    for source in sources():
        if not any(line.startswith(("%", "!")) for line in source.splitlines()):
            compile(source, "notebook", "exec")
    for name, source in blocks().items():
        compile(source, name, "exec")


def test_question_revision_is_development_only() -> None:
    original = json.loads((ROOT / "configs/mercury_selection_questions_v2.json").read_text())
    revision = BUILDER["revised_questions"]()
    assert revision["split"] == "development"
    assert revision["version"] == "mercury-selection-value-dev-2.0-en"
    assert revision["questions"] == original["questions"]
    assert all("{crater}" in q["text"] for q in revision["questions"])


def test_historical_settings_restored() -> None:
    controls = next(s for s in sources() if "TARGET_IDS = [16604" in s)
    namespace = {}
    exec(controls, namespace)
    expected = {
        "BUDGET": 4,
        "SEED": 42,
        "MAX_MODALITIES": 2,
        "RANDOM_DRAWS": 5,
        "IMAGE_EDGE": 448,
        "ANSWER_TOKENS": 1024,
        "SELECTOR_TOKENS": 512,
        "ITERATIVE_SELECTOR_TOKENS": 512,
        "MAX_INPUT_TOKENS": 8192,
        "ANSWER_REPETITION_PENALTY": 1.2,
    }
    for key, value in expected.items():
        assert namespace[key] == value
    install = next(s for s in sources() if "packages =" in s)
    for package in (
        "transformers==5.19.0",
        "Pillow==12.3.0",
        "accelerate==1.15.0",
        "bitsandbytes==0.50.2",
    ):
        assert package in install
    assert "5.20.2" not in install
    assert "DEVELOPMENT_OPTICAL_DESCRIPTION" not in blocks()["target_setup"]
    assert "ASSETS = describe_assets(" in blocks()["target_setup"]


@pytest.mark.parametrize("variant", ["updated", "previous"])
def test_iterative_extension_is_logged_without_mutating_evidence(variant: str) -> None:
    function = ast.parse(blocks()["iterative"]).body[0]
    calls = []

    def fake_generate(messages: list[dict], max_new_tokens: int) -> str:
        calls.append((messages, max_new_tokens))
        return "test-only"

    namespace = {
        "copy": copy,
        "SELECTOR_VARIANT": variant,
        "DEVELOPMENT_ALIGNMENT": BUILDER["ALIGNMENT"],
        "DEVELOPMENT_COMPLEMENTARITY": BUILDER["COMPLEMENTARITY"],
        "generate_reply": fake_generate,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "wrapper", "exec"), namespace)
    messages = [{"role": "system", "content": [{"type": "text", "text": "original rules"}]}]
    before = copy.deepcopy(messages)
    assert namespace["selector_generate_reply"](messages, 512) == "test-only"
    assert messages == before
    assert calls[0][1] == 512
    if variant == "updated":
        assert calls[0][0][0]["content"][-1]["text"] == (
            BUILDER["ALIGNMENT"] + " " + BUILDER["COMPLEMENTARITY"]
        )
    else:
        assert calls[0][0] == before
    assert "DEVELOPMENT_ALIGNMENT" not in blocks()["answer"]


@pytest.mark.parametrize("variant", ["typo", "", "formal"])
def test_controls_reject_unknown_variant(variant: str) -> None:
    controls = next(s for s in sources() if "TARGET_IDS = [16604" in s)
    controls = controls.replace('SELECTOR_VARIANT = "updated"', f"SELECTOR_VARIANT = {variant!r}")
    with pytest.raises(ValueError, match="Unknown selector variant"):
        exec(controls, {})


def test_controls_reject_heldout_target() -> None:
    controls = next(s for s in sources() if "TARGET_IDS = [16604" in s)
    controls = controls.replace("TARGET_IDS = [16604, 5031, 2179]", "TARGET_IDS = [999]")
    with pytest.raises(ValueError, match="development targets"):
        exec(controls, {})


def test_model_loading_and_generation_regressions() -> None:
    loading = next(s for s in sources() if "backbone_attention =" in s)
    assert 'backbone_attention = "sdpa"' in loading
    assert '"gemma4-native-sdpa"' in loading
    assert "revision=RESOLVED_MODEL_REVISION" in loading
    assert "AutoProcessor.from_pretrained(MODEL_ID, revision=RESOLVED_MODEL_REVISION)" in loading
    generation = next(s for s in sources() if "class GenerationTrace" in s)
    assert '{"use_model_defaults": False} if is_qwen else {}' in generation
    assert "generation_config=config" in generation
    assert "selector_generate_reply" in blocks()["experiment"]
    assert 'config["selector_variant"]' not in blocks()["experiment"]


def test_runner_three_targets_and_preserves_failed_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use metadata-only records; this is orchestration testing, not model inference."""
    runner = next(s for s in sources() if "for TARGET_ID in TARGET_IDS:" in s)
    calls = []
    namespace = {
        "EXECUTION_SOURCES": {key: key for key in blocks()},
        "RESULTS_ROOT": tmp_path,
        "RUN_LABEL": "fixture",
        "TARGET_IDS": [16604, 5031, 2179],
        "GENERATION_LOG": [],
        "torch": SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: None)),
    }

    class FakeShell:
        def run_cell(self, source: str) -> SimpleNamespace:
            target = namespace["TARGET_ID"]
            calls.append((target, source))
            folder = tmp_path / str(target)
            folder.mkdir(exist_ok=True)
            namespace.update(
                OUTPUT=folder,
                CASE_NAME=str(target),
                MODEL_TAG="fixture-model",
                Attempt=SimpleNamespace(
                    model_validate_json=lambda raw: SimpleNamespace(**json.loads(raw))
                ),
            )
            if source == "experiment":
                for i in range(36):
                    path = folder / f"Q1__fixture__r{i}.json"
                    if not path.exists():
                        path.write_text(json.dumps({"status": "error" if i == 0 else "success"}))
            return SimpleNamespace(raise_error=lambda: None)

    monkeypatch.setitem(sys.modules, "IPython", SimpleNamespace(get_ipython=lambda: FakeShell()))
    exec(runner, namespace)
    assert calls == [(target, stage) for target in (16604, 5031, 2179) for stage in blocks()]
    snapshots = {p: p.read_bytes() for p in tmp_path.rglob("Q*json")}
    assert len(snapshots) == 108
    exec(runner, namespace)
    assert all(p.read_bytes() == raw for p, raw in snapshots.items())
    namespace["EXECUTION_SOURCES"]["selector"] = "changed"
    with pytest.raises(ValueError, match="Execution code changed"):
        exec(runner, namespace)


def test_template_drift_is_not_silent() -> None:
    with pytest.raises(ValueError, match="Template anchor changed"):
        BUILDER["replace_once"]("missing", "anchor", "replacement")
