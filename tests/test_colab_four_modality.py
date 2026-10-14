"""Offline four-modality notebook routing and safe archive handling."""

import ast
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

import test_colab_notebook as base
from autonomous_modality import colab_four_modality as portable

NOTEBOOK = Path("notebooks/autonomous_modality_selection_four_modality.ipynb")


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Reuse explicit synthetic fixtures, then execute the new notebook functions."""
    ns = base.notebook_runtime.__wrapped__(tmp_path)
    monkeypatch.setattr(base, "NOTEBOOK", NOTEBOOK)
    ns["MS_TEXT"] = "SYNTHETIC_MULTISPECTRAL_NOT_OBSERVED"
    ns["MULTISPECTRAL_TEXT"] = ns["MS_TEXT"]
    spectral = ns["VIEW_DIR"] / "multispectral.txt"
    spectral.write_text(ns["MS_TEXT"], encoding="utf-8")
    ns["receipt"].output_sha256[spectral.name] = ns["sha256"](spectral)
    ns["receipt_path"].write_text(json.dumps(ns["receipt"].output_sha256), encoding="utf-8")
    ns["ASSETS"]["MULTISPECTRAL_IMAGE"] = {
        "cost": 2,
        "description": "Synthetic test fixture",
        "content_inventory": ns["ASSETS"]["TOPOGRAPHY"]["content_inventory"],
    }
    ns["ANSWER_REPETITION_PENALTY"] = 1.2
    original = ns["generate_reply"]

    def generate_reply(
        messages: list[dict], max_new_tokens: int = 128, repetition_penalty: float = 1.0
    ) -> str:
        assert repetition_penalty in (1.0, 1.2)
        return original(messages, max_new_tokens)

    ns["generate_reply"] = generate_reply
    for marker in ("class AgentChoice", "def build_answer_messages", "def select_inputs_iterative"):
        base.execute(base.cell_with(marker), ns)
    runner = base.cell_with("class Attempt")
    base.execute_nodes(
        runner, ns, [n for n in ast.parse(runner).body if isinstance(n, ast.ClassDef)]
    )
    return ns


def test_notebook_clean_and_compiles() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert "widgets" not in notebook["metadata"]
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            source = "".join(cell["source"])
            if not source.lstrip().startswith(("%", "!")):
                ast.parse(source)
            assert "SEARCH_LITERATURE" not in source


def test_complete_loop_and_resume(runtime: dict[str, Any]) -> None:
    base.test_all_36_attempts_and_resume(runtime)
    for path in runtime["OUTPUT"].glob("*ALL_AVAILABLE*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert len(record["selected"]) == 4
        assert record["input_cost"] == 7


@pytest.mark.parametrize(
    "wrapper", ["{}", "  {}\n", "```json\n{}\n```", "```\n{}\n```", "```json\r\n{}\r\n```"]
)
def test_one_shot_json_envelope(runtime: dict[str, Any], wrapper: str) -> None:
    raw = wrapper.format(json.dumps({"option_id": "S1", "rationale": "Fixture choice."}))
    assert runtime["parse_agent_choice"](raw).option_id == "S1"


@pytest.mark.parametrize(
    "raw",
    [
        'Here is JSON: {"option_id":"S1","rationale":"x"}',
        '```json\n{"option_id":"S1","rationale":"x"}\n```\nExtra text',
        "```json\n{}\n```\n```json\n{}\n```",
        '```python\n{"option_id":"S1","rationale":"x"}\n```',
        '```json\n{"option_id":"S1","rationale":"x"}',
        '```json\n{"option_id":"S1",}\n```',
        '```json\n{"option_id":1,"rationale":"x"}\n```',
        '```json\n{"option_id":"S1","rationale":"x","extra":true}\n```',
        '```json\n{"option_id":"S1"}\n```',
        "[]",
    ],
)
def test_one_shot_rejects_invalid_output(runtime: dict[str, Any], raw: str) -> None:
    with pytest.raises(ValueError):
        runtime["parse_agent_choice"](raw)


@pytest.mark.parametrize(
    "option, rationale, finish, valid",
    [
        ("S1", "Fixture choice.", "eos", True),
        ("UNKNOWN", "Fixture choice.", "eos", False),
        ("S1", "   ", "eos", False),
        ("S1", "Fixture choice.", "length", False),
    ],
)
def test_one_shot_keeps_raw_and_validation(
    runtime: dict[str, Any], option: str, rationale: str, finish: str, valid: bool
) -> None:
    raw = "```json\n" + json.dumps(dict(option_id=option, rationale=rationale)) + "\n```"
    calls = []

    def generate(messages: list[dict], max_new_tokens: int) -> str:
        calls.append(messages)
        runtime["GENERATION_LOG"].append(dict(text=raw, finish_reason=finish))
        return raw

    runtime["generate_reply"] = generate
    spec = runtime["QUESTIONS"][0]
    args = ("AGENT", spec["text"], spec["question_id"])
    if valid:
        selected, reason = runtime["select_inputs"](*args)
        assert selected == runtime["OPTIONS"][option]["selected"]
        assert reason == rationale
    else:
        with pytest.raises(ValueError):
            runtime["select_inputs"](*args)
    assert len(calls) == 1
    assert runtime["GENERATION_LOG"][-1]["text"] == raw


def test_one_shot_parser_is_fingerprinted() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    runner = next(
        "".join(c["source"])
        for c in notebook["cells"]
        if "tracked_objects = (" in "".join(c["source"])
    )
    assert "    parse_agent_choice,\n" in runner


def test_fenced_agent_complete_loop(runtime: dict[str, Any]) -> None:
    original = runtime["generate_reply"]

    def generate(
        messages: list[dict], max_new_tokens: int = 128, repetition_penalty: float = 1.0
    ) -> str:
        raw = original(messages, max_new_tokens, repetition_penalty)
        if '"feasible_options"' in messages[0]["content"][0].get("text", ""):
            raw = "```json\n" + raw + "\n```"
            runtime["GENERATION_LOG"][-1]["text"] = raw
        return raw

    runtime["generate_reply"] = generate
    base.test_all_36_attempts_and_resume(runtime)
    paths = list(runtime["OUTPUT"].glob("*__AGENT__*.json"))
    assert len(paths) == 4
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["selection_generations"][0]["text"].startswith("```json")


def test_routing_and_tamper(runtime: dict[str, Any]) -> None:
    build = runtime["build_answer_messages"]
    assert runtime["MS_TEXT"] not in json.dumps(build("fixture", [], []))
    spectral = build("fixture", [], ["MULTISPECTRAL_IMAGE"])
    assert runtime["MS_TEXT"] in json.dumps(spectral)
    assert not any(b["type"] == "image" for b in spectral[0]["content"])
    modality = runtime["InputDataModality"].MULTISPECTRAL_IMAGE
    observation = runtime["load_notebook_evidence"](modality)
    assert runtime["MS_TEXT"] in observation.blocks[0].text
    (runtime["VIEW_DIR"] / "multispectral.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError):
        runtime["load_notebook_evidence"](modality)


@pytest.mark.parametrize(
    "name",
    ["../escape", "/escape", "C:/escape", "wrong/file", "mercury-four-modality-20261006/../escape"],
)
def test_unsafe_archive_rejected(name: str) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, "fixture")
    with zipfile.ZipFile(stream) as archive, pytest.raises(ValueError, match="UNSAFE"):
        portable.safe_members(archive)


def test_safe_windows_archive() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(portable.DATASET_NAME + "\\fixture.txt", "fixture")
    with zipfile.ZipFile(stream) as archive:
        assert portable.safe_members(archive)[0].filename.endswith("/fixture.txt")


def test_checksum_and_edge_failures(tmp_path: Path) -> None:
    archive = tmp_path / "fake.zip"
    archive.write_bytes(b"synthetic invalid archive")
    with pytest.raises(ValueError, match="CHECKSUM"):
        portable.extract_dataset(archive, tmp_path)
    with pytest.raises(ValueError, match="EXISTING_ARCHIVE"):
        portable.download_archive(archive)
    with pytest.raises(ValueError, match="IMAGE_EDGE"):
        portable.prepare_compact_inputs(tmp_path, tmp_path / "views", 1)
