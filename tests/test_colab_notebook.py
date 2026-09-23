"""Execute notebook routing and experiment loops offline with explicitly fake inference."""

import ast
import copy
import gc
import hashlib
import json
import linecache
import time
import traceback
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, model_validator

from autonomous_modality.experiments import scenario_seed
from autonomous_modality.pilot import CatalogueRow

NOTEBOOK = Path("notebooks/autonomous_modality_selection_iterative.ipynb")


def code_cells() -> list[str]:
    """Read code only; notebook outputs and external files are never executed."""
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


def cell_with(marker: str) -> str:
    """Find one versioned notebook cell by a unique anchor."""
    cells = [c for c in code_cells() if marker in c]
    assert len(cells) == 1
    return cells[0]


def execute(source: str, namespace: dict[str, Any]) -> None:
    """Compile a cell with source available for inspection, like an IPython session."""
    name = f"<test-notebook-{hashlib.sha256(source.encode()).hexdigest()}>"
    linecache.cache[name] = (len(source), None, source.splitlines(True), name)
    exec(compile(source, name, "exec"), namespace)


def execute_nodes(source: str, namespace: dict[str, Any], nodes: list[ast.stmt]) -> None:
    """Execute only selected AST nodes, excluding GPU setup and actual inference."""
    tree = ast.Module(body=nodes, type_ignores=[])
    exec(compile(tree, "<notebook-test-nodes>", "exec"), namespace)


def test_notebook_is_clean_and_compiles() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert "widgets" not in notebook["metadata"]
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            source = "".join(cell["source"])
            if not source.lstrip().startswith(("%", "!")):
                ast.parse(source)
            assert "autonomous_modality.acquisition --" not in source
            assert "autonomous_modality.pilot --" not in source
    assert "use_model_defaults=False" in cell_with("def generate_reply")
    assert "do_sample=False" in cell_with("def generate_reply")
    assert 'RUN_LABEL = "emin-agentic-001"' in cell_with("class ViewReceipt")


@pytest.fixture
def notebook_runtime(tmp_path: Path) -> dict[str, Any]:
    """Invented text and placeholder image bytes; no model, GPU or scientific data."""
    root = tmp_path / "fixture-views"
    root.mkdir()
    names = ["optical_local", "optical_context", "elevation", "profile_east", "profile_north"]
    previews = {name: root / f"{name}.png" for name in names}
    for name, path in previews.items():
        path.write_bytes(f"SYNTHETIC_UNDECODED_TEST_IMAGE_{name}".encode())
    (root / "terrain.txt").write_text("SYNTHETIC_TERRAIN_ONLY", encoding="utf-8")
    catalogue = CatalogueRow(
        id=1,
        name="SYNTHETIC_NOT_OBSERVED",
        lat_n=0.0,
        lon_e_0=0.0,
        diameter=10.0,
        int_shp="x",
        rim_shp="x",
        cent_struc="x",
        rayed="n",
    )
    catalogue_path = tmp_path / "catalogue.json"
    catalogue_path.write_text(catalogue.model_dump_json(), encoding="utf-8")

    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    hashes = {p.name: sha256(p) for p in [*previews.values(), root / "terrain.txt"]}
    receipt_path = root / "receipt.json"
    receipt_path.write_text(json.dumps(hashes), encoding="utf-8")
    source_hashes = {"catalogue.json": sha256(catalogue_path)}
    specs = json.loads(Path("configs/mercury_questions_v1.json").read_text(encoding="utf-8"))[
        "questions"
    ]
    ns: dict[str, Any] = dict(
        __name__="notebook_fixture",
        Any=Any,
        Literal=Literal,
        BaseModel=BaseModel,
        ConfigDict=ConfigDict,
        Field=Field,
        model_validator=model_validator,
        CatalogueRow=CatalogueRow,
        catalogue=catalogue,
        json=json,
        copy=copy,
        time=time,
        gc=gc,
        traceback=traceback,
        scenario_seed=scenario_seed,
        sha256=sha256,
        ASSETS={
            m: dict(cost=c, description="Explicit test fixture")
            for m, c in [("CRATER_CATALOG", 1), ("OPTICAL_IMAGE", 2), ("TOPOGRAPHY", 2)]
        },
        MAX_MODALITIES=2,
        BUDGET=4,
        RANDOM_DRAWS=5,
        SEED=42,
        SELECTOR_TOKENS=256,
        ITERATIVE_SELECTOR_TOKENS=512,
        ANSWER_TOKENS=1024,
        GENERATION_LOG=[],
        CASE_ID="1",
        CASE_NAME=catalogue.name,
        MODEL_NAME="scripted-fixture",
        SELECTOR_TASK="fixture selection",
        ANSWER_POLICY="FIXTURE_SHARED_ANSWER_POLICY",
        PREVIEWS=previews,
        TERRAIN_TEXT="SYNTHETIC_TERRAIN_ONLY",
        CATALOGUE_TEXT=json.dumps(catalogue.model_dump(), ensure_ascii=False),
        QUESTIONS=specs,
        SOURCES={"catalogue.json": catalogue_path},
        SOURCE_HASHES=source_hashes,
        VIEW_DIR=root,
        receipt_path=receipt_path,
        receipt=SimpleNamespace(output_sha256=hashes),
        RUN_SHA256="a" * 64,
        OUTPUT=tmp_path / "results",
        torch=SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: None)),
        CONDITIONS=["NO_DATA", "ALL_AVAILABLE", "RANDOM", "AGENT", "AGENT_ITERATIVE"],
        fail_revision=False,
        request_second=False,
    )
    ns["OUTPUT"].mkdir()
    generation_cell = cell_with("class GenerationTrace")
    execute_nodes(
        generation_cell,
        ns,
        [n for n in ast.parse(generation_cell).body if isinstance(n, ast.ClassDef)],
    )

    def generate_reply(messages: list[dict], max_new_tokens: int = 128) -> str:
        trace = ns["GenerationTrace"](
            messages=copy.deepcopy(messages), max_new_tokens=max_new_tokens
        )
        if messages[0]["role"] == "system":
            payload = json.loads(messages[1]["content"][0]["text"])
            if payload["accessed_modalities"]:
                if ns["fail_revision"]:
                    trace.error = "SYNTHETIC_GENERATION_FAILURE"
                    ns["GENERATION_LOG"].append(trace.model_dump())
                    raise RuntimeError(trace.error)
                if ns["request_second"]:
                    reply = json.dumps(
                        dict(
                            action="REQUEST_MODALITY",
                            modality="TOPOGRAPHY",
                            information_gap="fixture second gap",
                            intended_use="fixture second use",
                            reason="fixture second acquisition",
                        )
                    )
                else:
                    reply = json.dumps(dict(action="FINISH", reason="fixture evidence sufficient"))
            else:
                reply = json.dumps(
                    dict(
                        action="REQUEST_MODALITY",
                        modality="OPTICAL_IMAGE",
                        information_gap="fixture gap",
                        intended_use="fixture use",
                        reason="FIXTURE_SELECTOR_SECRET",
                    )
                )
        elif '"feasible_options"' in messages[0]["content"][0].get("text", ""):
            reply = json.dumps(dict(option_id="S1", rationale="fixture one-shot choice"))
        else:
            reply = "TEST ANSWER; NOT A SCIENTIFIC OBSERVATION"
        trace.text, trace.finish_reason = reply, "eos"
        trace.input_tokens, trace.output_tokens = 20, 10
        ns["GENERATION_LOG"].append(trace.model_dump())
        return reply

    def write_new_json(path: Path, value: object) -> None:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)

    ns.update(generate_reply=generate_reply, write_new_json=write_new_json)
    execute(cell_with("class AgentChoice"), ns)
    execute(cell_with("def build_answer_messages"), ns)
    execute(cell_with("def select_inputs_iterative"), ns)
    runner = cell_with("class Attempt")
    execute_nodes(runner, ns, [n for n in ast.parse(runner).body if isinstance(n, ast.ClassDef)])
    return ns


def run_notebook_loop(namespace: dict[str, Any]) -> None:
    """Run the exact exported loop using the scripted test adapter."""
    runner = cell_with("class Attempt")
    nodes = [
        n
        for n in ast.parse(runner).body
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "spec"
    ]
    assert len(nodes) == 1
    execute_nodes(runner, namespace, nodes)


def test_all_36_attempts_and_resume(notebook_runtime: dict[str, Any]) -> None:
    ns = notebook_runtime
    run_notebook_loop(ns)
    paths = sorted(ns["OUTPUT"].glob("Q*__*.json"))
    records = [ns["Attempt"].model_validate_json(p.read_text(encoding="utf-8")) for p in paths]
    assert len(records) == 36
    assert Counter(r.condition for r in records) == {
        "NO_DATA": 4,
        "ALL_AVAILABLE": 4,
        "RANDOM": 20,
        "AGENT": 4,
        "AGENT_ITERATIVE": 4,
    }
    assert all(r.status == "success" for r in records)
    for record in records:
        if record.condition == "AGENT_ITERATIVE":
            assert record.iterative_selection.stop_actor == "agent"
            assert len(record.selection_generations) == 2
            assert record.input_cost == 2
        assert record.answer_generations[0].messages == ns["build_answer_messages"](
            record.question,
            next(
                q["answer_requirements"]
                for q in ns["QUESTIONS"]
                if q["question_id"] == record.question_id
            ),
            record.selected,
        )
        assert "FIXTURE_SELECTOR_SECRET" not in json.dumps(record.answer_generations[0].messages)
    before = {p: p.read_bytes() for p in paths}
    run_notebook_loop(ns)
    assert before == {p: p.read_bytes() for p in paths}


def test_failed_revision_is_saved_and_not_retried(notebook_runtime: dict[str, Any]) -> None:
    ns = notebook_runtime
    ns["CONDITIONS"] = ["AGENT_ITERATIVE"]
    ns["fail_revision"] = True
    run_notebook_loop(ns)
    paths = sorted(ns["OUTPUT"].glob("Q*__*.json"))
    assert len(paths) == 4
    for path in paths:
        record = ns["Attempt"].model_validate_json(path.read_text(encoding="utf-8"))
        assert record.status == "error" and record.error_stage == "selection"
        assert record.input_cost == 2 and record.selected == ["OPTICAL_IMAGE"]
        assert record.iterative_selection.stop_reason == "GENERATION_ERROR"
        assert len(record.selection_generations) == 2 and record.answer_generations == []
    ns["fail_revision"] = False
    run_notebook_loop(ns)
    assert all(json.loads(p.read_text(encoding="utf-8"))["status"] == "error" for p in paths)


def test_receipt_tamper_is_rejected(notebook_runtime: dict[str, Any]) -> None:
    ns = notebook_runtime
    ns["PREVIEWS"]["optical_local"].write_bytes(b"CHANGED_FIXTURE")
    with pytest.raises(ValueError, match="Input view changed"):
        ns["load_notebook_evidence"](ns["InputDataModality"].OPTICAL_IMAGE)


@pytest.mark.parametrize("budget,status,cost", [(4, "success", 4), (3, "error", 2)])
def test_notebook_second_acquisition_budget(
    notebook_runtime: dict[str, Any], budget: int, status: str, cost: int
) -> None:
    ns = notebook_runtime
    ns.update(BUDGET=budget, request_second=True, CONDITIONS=["AGENT_ITERATIVE"])
    run_notebook_loop(ns)
    for path in ns["OUTPUT"].glob("Q*__*.json"):
        record = ns["Attempt"].model_validate_json(path.read_text(encoding="utf-8"))
        assert record.status == status and record.input_cost == cost
        assert record.iterative_selection.stop_actor == "system"
        if status == "success":
            assert record.iterative_selection.stop_reason == "ACQUISITION_LIMIT"
            assert len(record.selection_generations) == 2
            assert (
                sum(
                    b["type"] == "image"
                    for b in record.answer_generations[0].messages[0]["content"]
                )
                == 5
            )
        else:
            assert record.iterative_selection.stop_reason == "CUMULATIVE_BUDGET_EXCEEDED"
            assert not record.answer_generations
