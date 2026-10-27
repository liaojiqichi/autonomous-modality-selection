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


@pytest.mark.parametrize(
    "text,expected",
    [
        ("**Proposed Checks & Evidence Basis**", True),
        ("## Additional-data proposals", True),
        ("__Methods__", True),
        ("- **Floor check**: Compare supplied values.", False),
        ("**The floor is flat.**", False),
        ("A plain scientific statement", False),
    ],
)
def test_explicit_heading_detection(text: str, expected: bool) -> None:
    from autonomous_modality.evidence_revision import is_standalone_heading

    assert is_standalone_heading(text) is expected


def test_missing_sources_are_excluded_without_changing_raw_audit() -> None:
    request, initial = fixture()
    initial = initial.model_copy(update={"answer": "**Methods**\nA proposal.\nAn observation."})
    request.assets[0].limitations = ["No age measurements supplied."]
    payload = {
        "claims": {
            "S2": {"verdict": "proposed", "sources": [], "reason": "Proposed work."},
            "S3": {"verdict": "supported", "sources": [], "reason": "Observation."},
        }
    }
    calls = []

    def generate(messages: list[dict], tokens: int) -> GenerationReply:
        calls.append(messages)
        if len(calls) == 1:
            context = json.loads(messages[1]["content"][0]["text"])
            assert context["required_statement_ids"] == ["S2", "S3"]
            assert "S1" not in context["statements"]
            assert context["selected_asset_capabilities"][0]["limitations"] == [
                "No age measurements supplied."
            ]
            assert len(context["selected_asset_capabilities"]) == 1
            return GenerationReply(text=json.dumps(payload), finish_reason="eos")
        context = json.loads(messages[1]["content"][0]["text"])
        assert context["retained_statements"] == []
        assert context["removed_statement_count"] == 2
        return GenerationReply(
            text=json.dumps(
                {
                    "action": "KEEP",
                    "option_id": None,
                    "reason": "Correct the answer.",
                    "remaining_value": "None retained",
                    "evidence_gap": "Reassess supplied evidence",
                }
            ),
            finish_reason="eos",
        )

    def answer(selected: list[str], retained: list[dict]) -> GenerationReply:
        assert retained == []
        return GenerationReply(text="Revised fixture answer", finish_reason="eos")

    result = run_answer_revision(
        request,
        initial,
        RevisionPolicy(),
        lambda name: [{"type": "text", "text": "fixture evidence"}],
        generate,
        answer,
        execution_kind="test",
    )
    assert result.status == "success"
    assert result.audit.model_dump() == payload
    assert result.statements["S1"] == "**Methods**"
    assert result.excluded_statements == {
        "S1": "STANDALONE_HEADING",
        "S2": "RETAINED_CLAIM_REQUIRES_SOURCE",
        "S3": "RETAINED_CLAIM_REQUIRES_SOURCE",
    }
    assert len(calls) == 2
    assert RevisionResult.model_validate_json(result.model_dump_json()) == result


def test_malformed_audit_json_is_still_rejected() -> None:
    from autonomous_modality.evidence_revision import parse_object

    with pytest.raises(json.JSONDecodeError):
        parse_object('{"claims":')


@pytest.mark.parametrize("same_set", [True, False])
def test_reviewer_explanation_defects_do_not_change_selected_evidence(same_set: bool) -> None:
    from autonomous_modality.evidence_revision import normalize_review_decision

    request, initial = fixture()
    options = final_options(request, initial)
    selected = initial.selected if same_set else ["OPTICAL_IMAGE", "TOPOGRAPHY"]
    oid = next(k for k, o in options.items() if o["selected"] == selected)
    raw = {
        "action": "RESELECT",
        "option_id": oid,
        "reason": "x" * 401,
        "remaining_value": 3.0,
        "evidence_gap": "No age measurement supplied.",
    }
    original = json.dumps(raw)
    decision, changes = normalize_review_decision(raw, options, initial.selected)
    assert json.dumps(raw) == original
    assert decision.action == ("KEEP" if same_set else "RESELECT")
    assert decision.option_id == (None if same_set else oid)
    assert len(decision.reason) == 400
    assert decision.remaining_value.startswith("Unavailable:")
    codes = {c.code for c in changes}
    assert "EXPLANATION_TOO_LONG" in codes and "EXPLANATION_INVALID_TYPE" in codes
    assert ("SAME_SELECTION_AS_INITIAL" in codes) is same_set


@pytest.mark.parametrize(
    "field,limit", [("reason", 400), ("remaining_value", 600), ("evidence_gap", 600)]
)
@pytest.mark.parametrize("kind", ["valid", "long", "empty", "number", "null", "list", "bool"])
def test_explanation_boundaries(field: str, limit: int, kind: str) -> None:
    from autonomous_modality.evidence_revision import normalize_review_decision

    request, initial = fixture()
    raw = {
        "action": "KEEP",
        "option_id": None,
        "reason": "Keep inputs.",
        "remaining_value": "A test remains.",
        "evidence_gap": "Age unavailable.",
    }
    raw[field] = {
        "valid": "x" * limit,
        "long": "x" * (limit + 1),
        "empty": "  ",
        "number": 3.0,
        "null": None,
        "list": [],
        "bool": True,
    }[kind]
    decision, changes = normalize_review_decision(
        raw, final_options(request, initial), initial.selected
    )
    assert len(getattr(decision, field)) <= limit
    assert bool(changes) is (kind != "valid")


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("unknown", "UNKNOWN_FINAL_OPTION"),
        ("missing_option", "RESELECT_REQUIRES_OPTION"),
        ("conflict", "CONFLICTING_KEEP_OPTION"),
        ("missing_field", "REVIEW_FIELDS_MISMATCH"),
        ("extra", "REVIEW_FIELDS_MISMATCH"),
        ("action", "UNKNOWN_REVIEW_ACTION"),
    ],
)
def test_ambiguous_review_still_fails(mutation: str, error: str) -> None:
    from autonomous_modality.evidence_revision import normalize_review_decision

    request, initial = fixture()
    options = final_options(request, initial)
    raw = {
        "action": "KEEP",
        "option_id": None,
        "reason": "Keep inputs.",
        "remaining_value": "A test remains.",
        "evidence_gap": "Age unavailable.",
    }
    if mutation == "unknown":
        raw["option_id"] = "R999"
    if mutation == "missing_option":
        raw["action"] = "RESELECT"
    if mutation == "conflict":
        raw["option_id"] = next(k for k, o in options.items() if o["selected"] == ["OPTICAL_IMAGE"])
    if mutation == "missing_field":
        raw.pop("reason")
    if mutation == "extra":
        raw["score"] = 3
    if mutation == "action":
        raw["action"] = "OTHER"
    with pytest.raises(ValueError, match=error):
        normalize_review_decision(raw, options, initial.selected)


def test_normalized_keep_preserves_raw_action_and_still_generates_answer() -> None:
    request, initial = fixture()
    options = final_options(request, initial)
    oid = next(k for k, o in options.items() if o["selected"] == initial.selected)
    raw = {
        "action": "RESELECT",
        "option_id": oid,
        "reason": "x" * 401,
        "remaining_value": 3.0,
        "evidence_gap": "Missing measurements.",
    }
    calls = []
    answers = []

    def generate(messages: list[dict], tokens: int) -> GenerationReply:
        calls.append(messages)
        if len(calls) == 2:
            payload = json.loads(messages[1]["content"][0]["text"])
            assert payload["initial_option_id"] == oid
            assert payload["output_schema"]["properties"]["reason"]["maxLength"] == 400
            assert payload["output_schema"]["properties"]["remaining_value"]["type"] == "string"
        return GenerationReply(
            text=json.dumps(audit_payload() if len(calls) == 1 else raw), finish_reason="eos"
        )

    def answer(selected: list[str], retained: list[dict]) -> GenerationReply:
        answers.append(selected)
        return GenerationReply(text="Revised fixture answer", finish_reason="eos")

    r = run_answer_revision(
        request,
        initial,
        RevisionPolicy(),
        lambda n: [{"type": "text", "text": "fixture evidence"}],
        generate,
        answer,
        execution_kind="test",
    )
    assert r.status == "success" and r.action.action == "KEEP"
    assert r.reviewer_raw_object == raw
    assert json.loads(r.reviewer_generation.text) == raw
    assert len(r.reviewer_adjustments) == 3
    assert answers == [initial.selected] and len(calls) == 2
    assert r.costs.additional_access_cost == 0 and r.costs.final_cost_delta == 0
    assert r.quality_checks.scientific_validity == "not_independently_checked"
    assert r.quality_checks.evidence_fidelity == "not_independently_checked"
    assert r.quality_checks.audit_flagged_statement_ids == ["S2"]
    assert RevisionResult.model_validate_json(r.model_dump_json()) == r


def test_keep_with_matching_explicit_option_is_logged() -> None:
    from autonomous_modality.evidence_revision import normalize_review_decision

    request, initial = fixture()
    options = final_options(request, initial)
    oid = next(k for k, o in options.items() if o["selected"] == initial.selected)
    decision, changes = normalize_review_decision(
        {
            "action": "KEEP",
            "option_id": oid,
            "reason": "Keep inputs.",
            "remaining_value": "A test remains.",
            "evidence_gap": "Age unavailable.",
        },
        options,
        initial.selected,
    )
    assert decision.option_id is None
    assert changes[0].code == "KEEP_OPTION_MATCHES_INITIAL"
