"""Scripted responses and metadata fixtures, never scientific inference results."""

import json

import pytest
from pydantic import ValidationError

from autonomous_modality.answer_revision import (
    PROMPT,
    PROMPT_VERSION,
    InitialAnswer,
    RevisionAction,
    RevisionPolicy,
    RevisionResult,
    parse_revision_action,
    replacement_options,
    run_answer_revision,
)
from autonomous_modality.iterative import GenerationReply
from autonomous_modality.models import (
    CraterQuestion,
    CraterQuestionType,
    DataAssetProfile,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
)

NAMES = ["CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY", "MULTISPECTRAL_IMAGE"]


@pytest.fixture
def request_data() -> InputSelectionRequest:
    return InputSelectionRequest(
        question=CraterQuestion(
            question_id="fixture-Q1",
            text="Fixture question?",
            question_type=CraterQuestionType.GENERAL_CRATER_INVESTIGATION,
            answer_requirements=["Use supplied features"],
        ),
        assets=[
            DataAssetProfile(
                asset_id=n,
                modality=InputDataModality(n),
                title="Test metadata",
                estimated_cost=1 if n == "CRATER_CATALOG" else 2,
            )
            for n in NAMES
        ],
        constraints=InputSelectionConstraints(maximum_modalities=2, maximum_total_cost=4),
    )


@pytest.fixture
def initial() -> InitialAnswer:
    return InitialAnswer(
        model="fixture-model",
        case_id="fixture",
        question_id="Q1",
        question="Fixture question?",
        selected=["CRATER_CATALOG", "TOPOGRAPHY"],
        answer="Original fixture answer",
        source_path="fixture.json",
        source_record_sha256="a" * 64,
        source_metadata_sha256="b" * 64,
    )


def reply(text: str, finish_reason: str = "eos") -> GenerationReply:
    return GenerationReply(text=text, finish_reason=finish_reason)


def test_keep_has_no_answer_call(
    request_data: InputSelectionRequest, initial: InitialAnswer
) -> None:
    seen = []

    def generate(messages: list[dict], tokens: int) -> GenerationReply:
        seen.extend(messages)
        assert tokens == 512
        return reply('{"action":"KEEP","option_id":null,"reason":"Sufficient evidence."}')

    def forbidden(selected: list[str]) -> GenerationReply:
        pytest.fail("KEEP must not call answer generation")

    result = run_answer_revision(
        request_data,
        initial,
        RevisionPolicy(),
        [{"type": "text", "text": "Fixture evidence"}],
        generate,
        forbidden,
        execution_kind="test",
    )
    assert result.status == "success"
    assert result.answer == initial.answer
    assert result.answer_origin == "initial"
    assert result.cumulative_access_cost == 3
    assert result.additional_access_cost == 0
    assert seen[0]["content"][0]["text"] == PROMPT
    assert PROMPT_VERSION == "answer-revision-evidence-retention-1.1"
    assert "Do not treat replacement as addition" in PROMPT
    assert "it does not\ncertify answer quality or correct errors" in PROMPT
    payload = json.loads(seen[1]["content"][0]["text"])
    assert payload["initial_answer"] == initial.answer
    assert payload["answer_requirements"] == ["Use supplied features"]
    assert seen[1]["content"][1]["text"] == "Fixture evidence"
    assert RevisionResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "selected,total,extra",
    [
        (["OPTICAL_IMAGE", "TOPOGRAPHY"], 5, 2),
        (["MULTISPECTRAL_IMAGE", "OPTICAL_IMAGE"], 7, 4),
        (["CRATER_CATALOG"], 3, 0),
    ],
)
def test_reselection_union_costs_and_isolation(
    request_data: InputSelectionRequest,
    initial: InitialAnswer,
    selected: list[str],
    total: int,
    extra: int,
) -> None:
    policy = RevisionPolicy()
    options = replacement_options(request_data, initial, policy)
    option_id = next(k for k, v in options.items() if v.selected == selected)
    answer_calls = []

    def generate(messages: list[dict], tokens: int) -> GenerationReply:
        return reply(
            json.dumps({"action": "RESELECT", "option_id": option_id, "reason": "New test."})
        )

    def answer(chosen: list[str]) -> GenerationReply:
        answer_calls.append(chosen)
        return reply("Fresh fixture answer")

    result = run_answer_revision(
        request_data, initial, policy, [], generate, answer, execution_kind="test"
    )
    assert result.status == "success"
    assert answer_calls == [selected]
    assert result.cumulative_access_cost == total
    assert result.additional_access_cost == extra
    assert result.answer_origin == "regenerated"
    assert set(result.accessed_modalities) == set(selected) | set(initial.selected)


def test_budget_and_required_options(
    request_data: InputSelectionRequest, initial: InitialAnswer
) -> None:
    options = replacement_options(request_data, initial, RevisionPolicy(maximum_cumulative_cost=4))
    assert all(set(o.selected) <= set(initial.selected) for o in options.values())
    request_data.constraints.required_modalities = {InputDataModality.CRATER_CATALOG}
    options = replacement_options(request_data, initial, RevisionPolicy())
    assert all("CRATER_CATALOG" in o.selected for o in options.values())
    assert not any(set(o.selected) == set(initial.selected) for o in options.values())


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"KEEP","option_id":"R1","reason":"x"}',
        '{"action":"RESELECT","option_id":null,"reason":"x"}',
        '{"action":"KEEP","option_id":null,"reason":" "}',
        '{"action":"KEEP","option_id":null,"reason":"x","extra":1}',
        '{"action":"KEEP","option_id":"none","reason":"x"}',
        'prefix {"action":"KEEP","option_id":null,"reason":"x"}',
        "```json\n{}\n``` trailing",
    ],
)
def test_strict_actions(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_revision_action(raw)


def test_single_fence() -> None:
    value = RevisionAction(action="KEEP", option_id=None, reason="Good")
    assert parse_revision_action("```json\n" + value.model_dump_json() + "\n```") == value


@pytest.mark.parametrize(
    "text,finish",
    [
        ("{}", "eos"),
        ("{}", "length"),
        ('{"action":"RESELECT","option_id":"UNKNOWN","reason":"x"}', "eos"),
    ],
)
def test_failure_no_retry(
    request_data: InputSelectionRequest, initial: InitialAnswer, text: str, finish: str
) -> None:
    calls = []

    def generate(messages: list[dict], tokens: int) -> GenerationReply:
        calls.append(1)
        return reply(text, finish)

    def answer(selected: list[str]) -> GenerationReply:
        pytest.fail("Invalid review must not generate an answer")

    result = run_answer_revision(
        request_data, initial, RevisionPolicy(), [], generate, answer, execution_kind="test"
    )
    assert result.status == "error" and result.error_stage == "review"
    assert len(calls) == 1
    assert result.reviewer_generation.text == text


@pytest.mark.parametrize("finish,status", [("length", "truncated"), ("unknown", "incomplete")])
def test_answer_truncation(
    request_data: InputSelectionRequest, initial: InitialAnswer, finish: str, status: str
) -> None:
    result = run_answer_revision(
        request_data,
        initial,
        RevisionPolicy(),
        [],
        lambda messages, tokens: reply('{"action":"RESELECT","option_id":"R1","reason":"x"}'),
        lambda selected: reply("Unfinished answer", finish),
        execution_kind="test",
    )
    assert result.status == status


def test_failed_answer_keeps_charge(
    request_data: InputSelectionRequest, initial: InitialAnswer
) -> None:
    options = replacement_options(request_data, initial, RevisionPolicy())
    key = next(k for k, v in options.items() if v.cumulative_access_cost == 7)

    def fail(selected: list[str]) -> GenerationReply:
        raise RuntimeError("Simulated memory error")

    result = run_answer_revision(
        request_data,
        initial,
        RevisionPolicy(),
        [],
        lambda messages, tokens: reply(
            json.dumps({"action": "RESELECT", "option_id": key, "reason": "Test"})
        ),
        fail,
        execution_kind="test",
    )
    assert result.status == "error"
    assert result.error_stage == "answer"
    assert result.cumulative_access_cost == 7
    assert result.answer is None


def test_invalid_initial(request_data: InputSelectionRequest, initial: InitialAnswer) -> None:
    initial.selected = ["CRATER_CATALOG", "CRATER_CATALOG"]
    with pytest.raises(ValueError, match="INVALID_INITIAL"):
        replacement_options(request_data, initial, RevisionPolicy())
    with pytest.raises(ValidationError):
        RevisionPolicy(maximum_revisions=2)


def test_keep_tampering_rejected(
    request_data: InputSelectionRequest, initial: InitialAnswer
) -> None:
    result = run_answer_revision(
        request_data,
        initial,
        RevisionPolicy(),
        [],
        lambda messages, tokens: reply('{"action":"KEEP","option_id":null,"reason":"x"}'),
        lambda selected: reply("Unused"),
        execution_kind="test",
    )
    data = result.model_dump()
    data["answer"] = "Tampered"
    with pytest.raises(ValueError, match="KEEP_MUST"):
        RevisionResult.model_validate(data)
