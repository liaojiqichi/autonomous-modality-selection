"""Offline formal-runner checks using metadata and explicitly synthetic inference."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import test_colab_four_modality as four
import test_colab_notebook as base
from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import QuestionSet
from autonomous_modality.heldout_colab import (
    Deployment,
    FormalContext,
    RuntimeApproval,
    load_approval,
    preserve_json,
)
from autonomous_modality.heldout_protocol import MODELS, FrozenProtocol, freeze_design
from test_heldout_protocol import fixture_cohort

BOOK = Path("notebooks/autonomous_modality_selection_heldout.ipynb")


def template_sources() -> dict[str, str]:
    result = {}
    for c in json.loads(BOOK.read_text(encoding="utf-8"))["cells"]:
        if c["cell_type"] != "code":
            continue
        for node in ast.parse("".join(c["source"])).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name.endswith("_SOURCE"):
                    result[name] = ast.literal_eval(node.value)
    return result


def context() -> FormalContext:
    cohort = fixture_cohort()
    questions = QuestionSet.model_validate_json(
        Path("configs/mercury_selection_questions_v2.json").read_bytes()
    )
    return FormalContext(
        cohort=cohort,
        questions=questions,
        design=freeze_design(cohort, questions),
        protocol=FrozenProtocol(question_sha256="a" * 64, cohort_sha256="b" * 64, pinned_files={}),
    )


def test_batches_and_all_draws() -> None:
    formal = context()
    batches = [formal.batch_ids(i) for i in range(1, 6)]
    assert all(len(b) == 6 for b in batches)
    assert [x for b in batches for x in b] == [t.id for t in formal.cohort.targets]
    for scenario in formal.design.scenarios:
        for budget in (3, 4):
            for draw in range(5):
                assert (
                    formal.random_choice(str(scenario.case_id), scenario.question_id, budget, draw)
                    == getattr(scenario, f"random_budget_{budget}")[draw]
                )


@pytest.mark.parametrize("batch", [0, 6, -1, True, "1"])
def test_invalid_batch(batch: object) -> None:
    with pytest.raises(ValueError):
        context().batch_ids(batch)


@pytest.mark.parametrize(
    "case,q,budget,draw",
    [("bad", "Q1", 4, 0), ("40000", "Q5", 4, 0), ("40000", "Q1", 2, 0), ("40000", "Q1", 4, 5)],
)
def test_invalid_draw(case: str, q: str, budget: int, draw: int) -> None:
    with pytest.raises(ValueError):
        context().random_choice(case, q, budget, draw)


def test_notebook_compiles_and_reuses_generation() -> None:
    book = json.loads(BOOK.read_text(encoding="utf-8"))
    assert "widgets" not in book["metadata"]
    for cell in book["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            ast.parse("".join(cell["source"]))
    templates = template_sources()
    assert len(templates) == 5
    for source in templates.values():
        ast.parse(source)
    assert "prepare_compact_inputs" not in templates["TARGET_SETUP_SOURCE"]
    assert '"held_out_from_model_development"' in templates["TARGET_SETUP_SOURCE"]
    assert "FORMAL.random_choice" in templates["SELECTOR_SOURCE"]
    assert "scenario_seed(" not in templates["SELECTOR_SOURCE"]
    assert "preflight_path" not in templates["EXPERIMENT_SOURCE"]
    functions = []
    for path in (BOOK, four.NOTEBOOK):
        cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
        source = next(
            "".join(c["source"]) for c in cells if "class GenerationTrace" in "".join(c["source"])
        )
        fn = next(
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name == "generate_reply"
        )
        functions.append(ast.dump(fn, include_attributes=False))
    assert functions[0] == functions[1]


def test_runtime_approval_and_tampering(tmp_path: Path) -> None:
    (tmp_path / "protocol.json").write_text("{}", encoding="utf-8")
    (tmp_path / "validation.json").write_text("SYNTHETIC TEST ARTIFACT", encoding="utf-8")
    deployment = Deployment(
        model_revision="a" * 40,
        processor_revision="b" * 40,
        environment=dict.fromkeys(
            ("torch", "transformers", "bitsandbytes", "accelerate", "Pillow"), "fixture"
        ),
        image_processor_size={"longest_edge": 102400},
        validation_file="validation.json",
        validation_sha256=sha256_file(tmp_path / "validation.json"),
        validation_split="development",
        reviewed_pass=True,
        validation_notes="Synthetic approval fixture; not model inference.",
    )
    approval = RuntimeApproval(
        version="heldout-runtime-approval-1",
        approved_by="TEST FIXTURE",
        protocol_sha256=sha256_file(tmp_path / "protocol.json"),
        notebook_sha256=sha256_file(BOOK),
        models={m: deployment for m in MODELS},
    )
    path = tmp_path / "approval.json"
    path.write_text(approval.model_dump_json(), encoding="utf-8")
    assert load_approval(path, tmp_path, BOOK) == approval
    (tmp_path / "validation.json").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="RELEASE_FILE_CHANGED"):
        load_approval(path, tmp_path, BOOK)
    with pytest.raises(ValidationError):
        Deployment.model_validate({**deployment.model_dump(), "reviewed_pass": False})
    with pytest.raises(ValidationError):
        Deployment.model_validate({**deployment.model_dump(), "model_revision": "main"})


def test_preserve_lock(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    preserve_json(path, {"budget": 4})
    before = path.read_bytes()
    preserve_json(path, {"budget": 4})
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="FORMAL_LOCK_CHANGED"):
        preserve_json(path, {"budget": 3})


@pytest.fixture
def formal_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    ns = four.runtime.__wrapped__(tmp_path, monkeypatch)
    templates = template_sources()
    ns["FORMAL"] = SimpleNamespace(
        random_choice=lambda case, q, budget, draw: ["MULTISPECTRAL_IMAGE"]
    )
    for name in ("SELECTOR_SOURCE", "ANSWER_SOURCE", "ITERATIVE_SOURCE"):
        base.execute(templates[name], ns)
    runner = templates["EXPERIMENT_SOURCE"]
    base.execute_nodes(
        runner, ns, [n for n in ast.parse(runner).body if isinstance(n, ast.ClassDef)]
    )
    monkeypatch.setattr(
        base, "cell_with", lambda marker: next(s for s in templates.values() if marker in s)
    )
    return ns


def test_full_formal_loop_and_resume(formal_runtime: dict) -> None:
    base.test_all_36_attempts_and_resume(formal_runtime)
    for path in formal_runtime["OUTPUT"].glob("*RANDOM*.json"):
        record = json.loads(path.read_bytes())
        assert record["selected"] == ["MULTISPECTRAL_IMAGE"]
        assert record["record_version"] == "colab-ap-heldout-four-modality-1"


def test_failed_formal_attempts_are_preserved(formal_runtime: dict) -> None:
    base.test_failed_revision_is_saved_and_not_retried(formal_runtime)


def test_six_target_controller(formal_runtime: dict, tmp_path: Path) -> None:
    """Exercise the real outer loop; synthetic setup replaces planetary file access."""
    ns = formal_runtime
    templates = template_sources()
    ns.update(templates)
    ns.update(
        RESULTS_ROOT=tmp_path,
        RUN_LABEL="batch",
        MODEL_TAG="fake-model",
        BATCH_TARGET_IDS=list(range(40000, 40006)),
    )

    def run_cell(source: str, store_history: bool) -> SimpleNamespace:
        assert store_history
        if source == templates["TARGET_SETUP_SOURCE"]:
            ns["CASE_ID"] = str(ns["TARGET_ID"])
            ns["OUTPUT"] = tmp_path / "batch/fake-model" / f"crater-{ns['TARGET_ID']}" / "budget-4"
            ns["OUTPUT"].mkdir(parents=True, exist_ok=True)
        elif source == templates["EXPERIMENT_SOURCE"]:
            base.run_notebook_loop(ns)
        else:
            base.execute(source, ns)
        return SimpleNamespace(raise_error=lambda: None)

    ns["batch_shell"] = SimpleNamespace(run_cell=run_cell)
    book = json.loads(BOOK.read_text(encoding="utf-8"))
    source = next(
        "".join(c["source"])
        for c in book["cells"]
        if "for TARGET_ID in BATCH_TARGET_IDS:" in "".join(c["source"])
    )
    loop = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "TARGET_ID"
    )
    base.execute_nodes(source, ns, [loop])
    paths = list((tmp_path / "batch").rglob("Q*__*.json"))
    assert len(paths) == 216
    before = {p: p.read_bytes() for p in paths}
    base.execute_nodes(source, ns, [loop])
    assert all(p.read_bytes() == contents for p, contents in before.items())
