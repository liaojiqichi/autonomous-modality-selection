"""Offline synthetic fixtures; these tests never run a real model or use planetary data."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_modality.development_sweep import (
    Combination,
    SweepAttempt,
    SweepPlan,
    SweepScenario,
    enumerate_combinations,
    file_sha256,
    planned_combinations,
    run_sweep,
)
from autonomous_modality.models import (
    CraterQuestion,
    DataAssetProfile,
    InputSelectionConstraints,
    InputSelectionRequest,
)


def scenario(budget: float = 4) -> SweepScenario:
    """Create three metadata-only artificial assets."""
    return SweepScenario(
        request=InputSelectionRequest(
            question=CraterQuestion(
                question_id="fixture",
                text="Synthetic question",
                question_type="GENERAL_CRATER_INVESTIGATION",
            ),
            assets=[
                DataAssetProfile(
                    asset_id=name, modality=name, title="SYNTHETIC", estimated_cost=cost
                )
                for name, cost in [("CRATER_CATALOG", 1), ("OPTICAL_IMAGE", 2), ("TOPOGRAPHY", 2)]
            ],
            constraints=InputSelectionConstraints(maximum_modalities=2, maximum_total_cost=budget),
        ),
        answer_requirements=["Propose a test"],
    )


@pytest.mark.parametrize("budget,count", [(4, 6), (3, 5), (2, 3), (1, 1), (0, 0)])
def test_combinations(budget: float, count: int) -> None:
    items = enumerate_combinations(scenario(budget).request)
    assert len(items) == count
    assert all(0 < len(x.selected) <= 2 and x.total_cost <= budget for x in items)
    assert len({tuple(x.selected) for x in items}) == count


def test_hard_constraints_and_controls() -> None:
    s = scenario()
    s.request.constraints.required_modalities = {"TOPOGRAPHY"}
    s.request.constraints.forbidden_modalities = {"OPTICAL_IMAGE"}
    assert [r.selected for r in enumerate_combinations(s.request)] == [
        ["TOPOGRAPHY"],
        ["CRATER_CATALOG", "TOPOGRAPHY"],
    ]
    rows = planned_combinations(scenario(), True)
    assert len(rows) == 8 and rows[-1].total_cost == 5 and rows[-2].selected == []
    assert rows[-1].role != "feasible"
    s.request.assets[-1].availability = "CASE_SPECIFIC"
    assert enumerate_combinations(s.request) == []


def plan(tmp_path: Path) -> SweepPlan:
    """Pin one tiny synthetic evidence file."""
    evidence = tmp_path / "fixture.txt"
    evidence.write_text("SYNTHETIC_NOT_OBSERVED", encoding="utf-8")
    return SweepPlan(
        execution_kind="test",
        model_id="scripted-fixture",
        scenarios=[scenario()],
        evidence_files={str(evidence): file_sha256(evidence)},
        generation_snapshot={
            "answer_function": "fixture",
            "generate_function": "fixture",
            "build_messages_function": "fixture",
            "config": {},
        },
    )


def messages(question: str, requirements: list[str], selected: list[str]) -> list[dict]:
    """A fabricated routing fixture with no conditions or rationales."""
    return [{"role": "user", "content": [question, requirements, selected]}]


def test_run_resume_and_config_change(tmp_path: Path) -> None:
    p = plan(tmp_path)
    log = []

    def answer(q: str, req: list[str], sel: list[str]) -> str:
        log.append(
            dict(messages=messages(q, req, sel), text="SYNTHETIC REPLY", finish_reason="eos")
        )
        return "SYNTHETIC REPLY"

    root = tmp_path / "new-run"
    results = run_sweep(p, root, answer, messages, log)
    assert len(results) == len(log) == 8
    assert all(x.status == "success" and x.execution_kind == "test" for x in results)
    assert run_sweep(p, root, answer, messages, log) == results
    assert len(log) == 8
    p.generation_snapshot["config"] = {"changed": True}
    with pytest.raises(ValueError, match="configuration changed"):
        run_sweep(p, root, answer, messages, log)


@pytest.mark.parametrize("mode", ["throw", "length", "bad_log", "empty", "no_log", "interrupt"])
def test_failures_are_preserved(tmp_path: Path, mode: str) -> None:
    p = plan(tmp_path)
    p.include_references = False
    log = []

    def answer(q: str, req: list[str], sel: list[str]) -> str:
        if mode == "throw":
            raise RuntimeError("Fixture failure")
        if mode == "interrupt":
            raise KeyboardInterrupt
        value = "" if mode == "empty" else "Fixture"
        if mode != "no_log":
            log.append(
                dict(
                    text=value,
                    messages=[] if mode == "bad_log" else messages(q, req, sel),
                    finish_reason="length" if mode == "length" else "eos",
                )
            )
        return value

    root = tmp_path / "run"
    if mode == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            run_sweep(p, root, answer, messages, log)
        attempts = [
            SweepAttempt.model_validate_json(f.read_text())
            for f in root.glob("*.json")
            if f.name != "sweep_plan.json"
        ]
        assert len(attempts) == 1 and attempts[0].status == "started"
    else:
        rows = run_sweep(p, root, answer, messages, log)
        assert {r.status for r in rows} == ({"truncated"} if mode == "length" else {"error"})
        previous = len(log)
        run_sweep(p, root, answer, messages, log)
        assert len(log) == previous


def test_tampered_evidence_and_plan_rejected(tmp_path: Path) -> None:
    p = plan(tmp_path)
    payload = p.model_dump()
    payload["split"] = "held_out"
    with pytest.raises(ValidationError):
        SweepPlan.model_validate(payload)
    payload = p.model_dump()
    payload["scenarios"] *= 2
    with pytest.raises(ValidationError):
        SweepPlan.model_validate(payload)
    Path(next(iter(p.evidence_files))).write_text("CHANGED", encoding="utf-8")
    with pytest.raises(ValueError, match="Evidence changed"):
        run_sweep(p, tmp_path / "run", lambda *_: "never", messages, [])
    assert not (tmp_path / "run").exists()


def test_snapshot_whitespace_is_preserved(tmp_path: Path) -> None:
    p = plan(tmp_path)
    p.generation_snapshot["answer_function"] = "  def fixture():\n    pass\n"
    roundtrip = SweepPlan.model_validate_json(p.model_dump_json())
    assert roundtrip.generation_snapshot == p.generation_snapshot


@pytest.mark.parametrize("selected", [[], ["UNKNOWN"], ["TOPOGRAPHY", "TOPOGRAPHY"]])
def test_invalid_combinations(selected: list[str]) -> None:
    with pytest.raises(ValidationError):
        Combination(selected=selected, total_cost=2)


def test_no_data_reference_cannot_spend() -> None:
    with pytest.raises(ValidationError):
        Combination(role="no_data_reference", selected=[], total_cost=1)


def test_unknown_finish_reason_is_not_success(tmp_path: Path) -> None:
    p = plan(tmp_path)
    log = []

    def answer(q: str, req: list[str], sel: list[str]) -> str:
        log.append(dict(messages=messages(q, req, sel), text="Fixture", finish_reason="unknown"))
        return "Fixture"

    assert all(
        r.status == "truncated" for r in run_sweep(p, tmp_path / "unknown", answer, messages, log)
    )
