"""Synthetic evidence fixtures; no scientific data or model inference."""

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_modality.answer_revision import InitialAnswer
from autonomous_modality.evidence_revision import (
    CostAccounting,
    EvidenceAudit,
    RevisionPolicy,
    RevisionResult,
    final_options,
    run_answer_revision,
    summarize_costs,
    validate_audit,
)
from autonomous_modality.iterative import GenerationReply
from autonomous_modality.models import (
    CraterQuestion,
    DataAssetProfile,
    InputSelectionConstraints,
    InputSelectionRequest,
)


def fixture() -> tuple[InputSelectionRequest, InitialAnswer]:
    request = InputSelectionRequest(
        question=CraterQuestion(
            question_id="Q1", text="Test question", question_type="GENERAL_CRATER_INVESTIGATION"
        ),
        assets=[
            DataAssetProfile(asset_id=n, modality=n, title=n, estimated_cost=c)
            for n, c in [("CRATER_CATALOG", 1), ("OPTICAL_IMAGE", 2), ("TOPOGRAPHY", 2)]
        ],
        constraints=InputSelectionConstraints(maximum_modalities=2, maximum_total_cost=3.0),
    )
    initial = InitialAnswer(
        model="fixture",
        case_id="1",
        question_id="Q1",
        question="Test question",
        selected=["CRATER_CATALOG"],
        answer="A retained proposal.\nAn invented age.",
        source_record_sha256="a" * 64,
        source_metadata_sha256="b" * 64,
        source_path="fixture",
    )
    return request, initial


def audit_payload() -> dict:
    return {
        "claims": {
            "S1": {
                "verdict": "proposed",
                "sources": [1],
                "reason": "Test proposal linked to input.",
            },
            "S2": {"verdict": "unsupported", "sources": [], "reason": "Age absent."},
        }
    }


@pytest.mark.parametrize(
    "action,selected",
    [
        ("KEEP", ["CRATER_CATALOG"]),
        ("RESELECT", ["OPTICAL_IMAGE", "TOPOGRAPHY"]),
        ("RESELECT", []),
    ],
)
def test_audit_always_revises_and_overruns_survive(action: str, selected: list[str]) -> None:
    request, initial = fixture()
    options = final_options(request, initial)
    chosen = next(k for k, o in options.items() if o["selected"] == selected)
    calls = []
    answers = []

    def load(name: str) -> list[dict]:
        return [{"type": "text", "text": "fixture value"}]

    def generate(messages: list[dict], tokens: int) -> GenerationReply:
        calls.append(messages)
        obj = (
            audit_payload()
            if len(calls) == 1
            else {
                "action": action,
                "option_id": None if action == "KEEP" else chosen,
                "reason": "Test decision",
                "remaining_value": "One test remains",
                "evidence_gap": "Test gap",
            }
        )
        return GenerationReply(text=json.dumps(obj), finish_reason="eos")

    def answer(names: list[str], retained: list[dict]) -> GenerationReply:
        answers.append((names, retained))
        return GenerationReply(text="Corrected fixture answer", finish_reason="eos")

    r = run_answer_revision(
        request, initial, RevisionPolicy(), load, generate, answer, execution_kind="test"
    )
    assert r.status == "success" and r.answer != initial.answer
    audit_input = json.loads(calls[0][1]["content"][0]["text"])
    assert list(audit_input["output_template"]["claims"]) == ["S1", "S2"]
    assert audit_input["evidence_registry"]["1"]["modality"] == "CRATER_CATALOG"
    assert len(answers) == 1 and len(r.retained_statements) == 1
    assert "An invented age" not in json.dumps(calls[1])
    assert r.selected == selected
    assert len(answers[0][1]) == (1 if action == "KEEP" else 0)
    assert r.costs.final_input_cost == sum(1 if n == "CRATER_CATALOG" else 2 for n in selected)
    assert (
        r.costs.cumulative_access_cost
        == r.costs.initial_input_cost + r.costs.additional_access_cost
    )
    summary = summarize_costs([r])
    assert summary["mean_final_input_cost"] == r.costs.final_input_cost
    assert summary["final_over_budget_successes"] == int(
        selected == ["OPTICAL_IMAGE", "TOPOGRAPHY"]
    )
    assert RevisionResult.model_validate_json(r.model_dump_json()) == r


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("missing", "missing=\\['S2'\\]"),
        ("extra", "extra=\\['S99'\\]"),
        ("source", "UNKNOWN_EVIDENCE"),
        ("duplicate_source", "DUPLICATE_EVIDENCE"),
        ("unsupported_retained", "RETAINED_CLAIM"),
    ],
)
def test_bad_audit_rejected(mutation: str, error: str) -> None:
    obj = audit_payload()
    if mutation == "missing":
        obj["claims"].pop("S2")
    if mutation == "extra":
        obj["claims"]["S99"] = obj["claims"]["S2"].copy()
    if mutation == "source":
        obj["claims"]["S1"]["sources"] = [99]
    if mutation == "duplicate_source":
        obj["claims"]["S1"]["sources"] = [1, 1]
    if mutation == "unsupported_retained":
        obj["claims"]["S2"]["verdict"] = "supported"
    with pytest.raises(ValueError, match=error):
        validate_audit(
            EvidenceAudit.model_validate(obj),
            {"S1": "a", "S2": "b"},
            {
                "1": {
                    "modality": "CRATER_CATALOG",
                    "block": {"type": "text", "text": "fixture value"},
                }
            },
        )


@pytest.mark.parametrize("source", [True, "1", 0, -1, 1.0])
def test_evidence_ids_are_strict_positive_integers(source: object) -> None:
    obj = audit_payload()
    obj["claims"]["S1"]["sources"] = [source]
    with pytest.raises(ValidationError):
        EvidenceAudit.model_validate(obj)


def test_duplicate_json_statement_cannot_be_silently_lost() -> None:
    from autonomous_modality.evidence_revision import parse_object

    with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
        parse_object('{"claims":{"S1":{},"S1":{}}}')


def test_image_reference_resolves_without_invented_locator() -> None:
    retained = validate_audit(
        EvidenceAudit.model_validate(audit_payload()),
        {"S1": "proposal", "S2": "unsupported"},
        {"1": {"modality": "OPTICAL_IMAGE", "block": {"type": "image", "image": "fixture.png"}}},
    )
    assert retained[0]["modalities"] == ["OPTICAL_IMAGE"]
    assert retained[0]["sources"] == [
        {"evidence_id": 1, "modality": "OPTICAL_IMAGE", "block_type": "image"}
    ]


def test_truncated_audit_stops_without_hidden_retry() -> None:
    request, initial = fixture()
    calls = []

    def generate(messages: list[dict], tokens: int) -> GenerationReply:
        calls.append(messages)
        return GenerationReply(text="{", finish_reason="length")

    def answer(selected: list[str], retained: list[dict]) -> GenerationReply:
        pytest.fail("No answer after incomplete audit")

    r = run_answer_revision(
        request, initial, RevisionPolicy(), lambda n: [], generate, answer, execution_kind="test"
    )
    assert r.status == "error" and r.error_stage == "audit" and len(calls) == 1


def test_over_budget_accounting_cannot_hide_overrun() -> None:
    with pytest.raises(ValidationError, match="FINAL_OVERRUN"):
        CostAccounting(
            initial_input_cost=1.0,
            final_input_cost=4.0,
            additional_access_cost=4.0,
            cumulative_access_cost=5.0,
            final_cost_delta=3.0,
            budget_threshold=3.0,
            final_over_budget=False,
            cumulative_over_budget=True,
        )


def test_generated_baselines_no_iterative_and_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import test_colab_notebook as base
    from test_heldout_colab import formal_runtime

    ns = formal_runtime.__wrapped__(tmp_path, monkeypatch)
    book = json.loads(
        Path("notebooks/autonomous_modality_selection_answer_revision_formal.ipynb").read_text(
            encoding="utf-8"
        )
    )
    sources = {}
    for cell in book["cells"]:
        s = "".join(cell["source"])
        if s.startswith(("EVIDENCE_SOURCE =", "EXPERIMENT_SOURCE =")):
            node = ast.parse(s).body[0]
            sources[node.targets[0].id] = ast.literal_eval(node.value)
    base.execute(sources["EVIDENCE_SOURCE"], ns)
    # Exercise the actual loop with synthetic model responses and existing protocol fixture.
    runner = sources["EXPERIMENT_SOURCE"]
    nodes = [
        n
        for n in ast.parse(runner).body
        if isinstance(n, ast.ClassDef)
        or (
            isinstance(n, ast.Assign)
            and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id == "CONDITIONS"
        )
        or (isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "spec")
    ]
    base.execute_nodes(runner, ns, nodes)
    paths = list(ns["OUTPUT"].glob("Q*__*.json"))
    assert len(paths) == 32
    assert all("AGENT_ITERATIVE" not in p.name for p in paths)
    before = {p: p.read_bytes() for p in paths}
    runner = sources["EXPERIMENT_SOURCE"]
    nodes = [
        n
        for n in ast.parse(runner).body
        if isinstance(n, ast.ClassDef)
        or (
            isinstance(n, ast.Assign)
            and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id == "CONDITIONS"
        )
        or (isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "spec")
    ]
    base.execute_nodes(runner, ns, nodes)
    assert all(p.read_bytes() == v for p, v in before.items())
