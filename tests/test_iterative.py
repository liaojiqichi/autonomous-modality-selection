"""Scripted model replies and invented evidence; no scientific results or network."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from autonomous_modality.development_inputs import development_inventory
from autonomous_modality.iterative import (
    AgentAction,
    CompactAgentAction,
    ContentBlock,
    EvidenceObservation,
    GenerationReply,
    IterativeAnswer,
    IterativePolicy,
    IterativeSelection,
    answer_messages,
    run_iterative_answer,
    run_iterative_selection,
    save_iterative_answer,
)
from autonomous_modality.iterative_colab import notebook_generator
from autonomous_modality.models import (
    AssetAvailability,
    CraterQuestion,
    CraterQuestionType,
    DataAssetProfile,
    InputSelectionConstraints,
    InputSelectionRequest,
)
from autonomous_modality.models import (
    InputDataModality as M,
)


@pytest.fixture
def request_data() -> InputSelectionRequest:
    """Three declared test assets with legacy test costs."""
    return InputSelectionRequest(
        question=CraterQuestion(
            question_id="fixture-Q1",
            text="How could this fixture be investigated?",
            question_type=CraterQuestionType.GENERAL_CRATER_INVESTIGATION,
        ),
        assets=[
            DataAssetProfile(
                asset_id=m.value, modality=m, title="TEST FIXTURE", estimated_cost=cost
            )
            for m, cost in [(M.CRATER_CATALOG, 1), (M.OPTICAL_IMAGE, 2), (M.TOPOGRAPHY, 2)]
        ],
        constraints=InputSelectionConstraints(maximum_modalities=2, maximum_total_cost=4),
    )


POLICY = IterativePolicy(cost_unit="legacy_ordinal_units", cost_definition="Test costs 1/2/2.")


def test_notebook_bridge() -> None:
    log: list[dict[str, Any]] = []

    def reply(messages: list[dict[str, object]], max_new_tokens: int) -> str:
        log.append(dict(text="fixture", finish_reason="eos", output_tokens=2))
        return "fixture"

    generate = notebook_generator(reply, log)
    assert generate([], 10).finish_reason == "eos"
    assert generate([], 10).output_tokens == 2
    assert len(log) == 2
    stale = notebook_generator(reply, [])
    with pytest.raises(ValueError, match="fresh"):
        stale([], 10)


def acquire(modality: str) -> str:
    """Return a scripted acquisition response."""
    return json.dumps(
        dict(
            action="REQUEST_MODALITY",
            modality=modality,
            reason="SECRET_SELECTOR_REASON",
        )
    )


STOP = '{"action":"FINISH","reason":"Fixture evidence is sufficient."}'


def fixture_observation(modality: M) -> EvidenceObservation:
    """Invented text stands in for real data only in offline unit tests."""
    return EvidenceObservation(
        modality=modality,
        blocks=[ContentBlock(type="text", text=f"FIXTURE_DATA_{modality}")],
        evidence_sha256={"fixture.txt": "a" * 64},
        package_sha256="b" * 64,
    )


class ScriptedGenerator:
    """Capture prompts and return predetermined test-only outputs."""

    def __init__(self, replies: list[str], finish: str = "eos") -> None:
        self.replies = iter(replies)
        self.messages: list[list[dict[str, object]]] = []
        self.finish = finish

    def __call__(self, messages: list[dict[str, object]], tokens: int) -> GenerationReply:
        self.messages.append(messages)
        return GenerationReply(
            text=next(self.replies), finish_reason=self.finish, input_tokens=10, output_tokens=5
        )


def run(request: InputSelectionRequest, generator: ScriptedGenerator) -> IterativeSelection:
    """Execute with an explicitly test-only generator and loader."""
    return run_iterative_selection(
        request,
        POLICY,
        generator,
        fixture_observation,
        model_id="scripted-fixture",
        execution_kind="test",
    )


def test_observe_then_acquire_and_answer(request_data: InputSelectionRequest) -> None:
    generator = ScriptedGenerator([acquire("OPTICAL_IMAGE"), acquire("TOPOGRAPHY")])
    result = run(request_data, generator)
    assert result.status == "ready"
    assert result.accessed_modalities == [M.OPTICAL_IMAGE, M.TOPOGRAPHY]
    assert result.cumulative_cost == 4
    assert result.stop_actor == "system" and result.stop_reason == "ACQUISITION_LIMIT"
    assert len(generator.messages) == 2
    assert "FIXTURE_DATA_" not in json.dumps(generator.messages[0])
    assert "FIXTURE_DATA_OPTICAL_IMAGE" in json.dumps(generator.messages[1])
    assert "FIXTURE_DATA_TOPOGRAPHY" not in json.dumps(generator.messages[1])
    prompt = json.dumps(answer_messages(result, "Shared answer prompt"))
    assert "FIXTURE_DATA_OPTICAL_IMAGE" in prompt and "FIXTURE_DATA_TOPOGRAPHY" in prompt
    assert "CRATER_CATALOG" not in prompt and "SECRET_SELECTOR_REASON" not in prompt
    assert "AGENT_ITERATIVE" not in prompt and "inventory" not in prompt
    assert IterativeSelection.model_validate_json(result.model_dump_json()) == result
    assert IterativeSelection.model_validate(json.loads(result.model_dump_json())) == result


def test_stop_after_observation(request_data: InputSelectionRequest) -> None:
    result = run(request_data, ScriptedGenerator([acquire("CRATER_CATALOG"), STOP]))
    assert result.stop_actor == "agent" and result.stop_reason == "AGENT_FINISH"
    assert result.cumulative_cost == 1 and len(result.turns) == 2
    assert IterativeSelection.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("reason", [" ", "x" * 241, 17, None])
def test_compact_reason_is_bounded(reason: object) -> None:
    with pytest.raises(ValidationError):
        CompactAgentAction.model_validate_json(json.dumps({"action": "FINISH", "reason": reason}))


def test_current_parser_rejects_legacy_fields_without_retry(
    request_data: InputSelectionRequest,
) -> None:
    payload = json.loads(acquire("TOPOGRAPHY"))
    payload.update(information_gap="legacy gap", intended_use="legacy use")
    generator = ScriptedGenerator([json.dumps(payload), STOP])
    result = run(request_data, generator)
    assert result.stop_reason == "INVALID_ACTION_JSON"
    assert result.cumulative_cost == 0 and len(generator.messages) == 1
    assert result.turns[0].generation.text == json.dumps(payload)


def test_malformed_revision_is_preserved_without_repair(
    request_data: InputSelectionRequest,
) -> None:
    malformed = '{"action":"REQUEST_MODALITY","modality":"OPTICAL_IMAGE","reason":"gap,""use":"x"}'
    generator = ScriptedGenerator([acquire("TOPOGRAPHY"), malformed, STOP])
    result = run(request_data, generator)
    assert result.stop_reason == "INVALID_ACTION_JSON" and result.status == "error"
    assert result.accessed_modalities == [M.TOPOGRAPHY] and result.cumulative_cost == 2
    assert len(generator.messages) == 2
    assert result.turns[-1].generation.text == malformed
    assert result.turns[-1].action is None


def test_legacy_trace_is_readable_without_rewriting(request_data: InputSelectionRequest) -> None:
    result = run(request_data, ScriptedGenerator([acquire("TOPOGRAPHY"), STOP]))
    payload = result.model_dump(mode="json")
    payload["schema_version"] = "iterative-selection-1.0"
    payload["prompt_version"] = "bounded-evidence-selector-ap-1.1-en"
    action = payload["turns"][0]["action"]
    action.update(information_gap="legacy gap", intended_use="legacy use")
    payload["turns"][1]["action"].update(information_gap=None, intended_use=None)
    payload["turns"][0]["generation"]["text"] = json.dumps(action)
    serialized = json.dumps(payload)
    historical = IterativeSelection.model_validate_json(serialized)
    assert isinstance(historical.turns[0].action, AgentAction)
    assert historical.schema_version == "iterative-selection-1.0"
    assert historical.turns[0].action.information_gap == "legacy gap"
    assert IterativeSelection.model_validate_json(historical.model_dump_json()) == historical
    payload["schema_version"] = "iterative-selection-1.1"
    with pytest.raises(ValidationError, match="versions differ"):
        IterativeSelection.model_validate_json(json.dumps(payload))


def test_inventory_precedes_acquisition_without_values(request_data: InputSelectionRequest) -> None:
    for asset in request_data.assets:
        asset.content_inventory = development_inventory(asset.modality)
    generator = ScriptedGenerator([STOP])
    result = run(request_data, generator)
    assert result.stop_actor == "agent" and result.cumulative_cost == 0
    message = json.loads(generator.messages[0][1]["content"][0]["text"])
    catalogue = next(a for a in message["inventory"] if a["modality"] == "CRATER_CATALOG")
    assert "crater_depth" in catalogue["content_inventory"]["absent_fields"]
    assert "absolute_age" in catalogue["content_inventory"]["absent_fields"]
    assert "diameter" in catalogue["content_inventory"]["available_fields"]
    assert "FIXTURE_DATA" not in json.dumps(generator.messages)


@pytest.mark.parametrize("needs_terrain,expected_count", [(True, 2), (False, 1)])
def test_observation_can_change_next_action(
    request_data: InputSelectionRequest, needs_terrain: bool, expected_count: int
) -> None:
    """A test policy reacts to returned content, not a preselected second action."""

    def loader(modality: M) -> EvidenceObservation:
        observation = fixture_observation(modality)
        if needs_terrain and modality == M.OPTICAL_IMAGE:
            observation.blocks.append(ContentBlock(type="text", text="FIXTURE_RELIEF_UNRESOLVED"))
        return observation

    calls = []

    def generate(messages: list[dict[str, object]], tokens: int) -> GenerationReply:
        text = json.dumps(messages)
        if not calls:
            reply = acquire("OPTICAL_IMAGE")
        else:
            reply = acquire("TOPOGRAPHY") if "FIXTURE_RELIEF_UNRESOLVED" in text else STOP
        calls.append(text)
        return GenerationReply(text=reply, finish_reason="eos")

    result = run_iterative_selection(
        request_data, POLICY, generate, loader, model_id="reactive-fixture", execution_kind="test"
    )
    assert result.status == "ready" and len(result.accessed_modalities) == expected_count
    assert len(calls) == 2


def test_verbatim_text() -> None:
    text = "  fixture text with source-span-sensitive whitespace\n"
    assert GenerationReply(text=text, finish_reason="eos").text == text
    assert ContentBlock(type="text", text=text).text == text


def test_generation_error_retains_first_turn(request_data: InputSelectionRequest) -> None:
    # Exhausted test generator raises on the second call.
    result = run(request_data, ScriptedGenerator([acquire("OPTICAL_IMAGE")]))
    assert result.status == "error" and result.stop_reason == "GENERATION_ERROR"
    assert result.cumulative_cost == 2 and len(result.turns) == 2


def test_failed_selection_prevents_answer(request_data: InputSelectionRequest) -> None:
    selection = run(request_data, ScriptedGenerator(["invalid"]))
    generator = ScriptedGenerator([])
    result = run_iterative_answer(selection, "shared prompt", generator, max_new_tokens=20)
    assert result.status == "error" and not generator.messages


def test_wrong_observation_rejected(request_data: InputSelectionRequest) -> None:
    result = run_iterative_selection(
        request_data,
        POLICY,
        ScriptedGenerator([acquire("OPTICAL_IMAGE")]),
        lambda modality: fixture_observation(M.TOPOGRAPHY),
        model_id="fixture",
        execution_kind="test",
    )
    assert result.status == "error" and result.stop_reason == "EVIDENCE_MODALITY_MISMATCH"
    assert result.turns[0].observation is None and result.cumulative_cost == 2


def test_invalid_saved_answer_status(request_data: InputSelectionRequest) -> None:
    selection = run(request_data, ScriptedGenerator([STOP]))
    result = run_iterative_answer(
        selection, "shared", ScriptedGenerator(["fixture"], "length"), max_new_tokens=20
    )
    payload = result.model_dump(mode="json")
    payload["status"] = "success"
    with pytest.raises(ValidationError, match="finish reason"):
        IterativeAnswer.model_validate(payload)


def test_initial_stop(request_data: InputSelectionRequest) -> None:
    result = run(request_data, ScriptedGenerator([STOP]))
    assert result.status == "ready" and result.accessed_modalities == []
    assert result.cumulative_cost == 0


@pytest.mark.parametrize(
    "second,code",
    [
        (acquire("OPTICAL_IMAGE"), "DUPLICATE_ACCESS"),
        ("not json", "INVALID_ACTION_JSON"),
        (acquire("SCIENTIFIC_LITERATURE"), "UNKNOWN_MODALITY"),
        ('{"action":"REPLACE","reason":"refund"}', "INVALID_ACTION_JSON"),
    ],
)
def test_failure_retains_access(
    request_data: InputSelectionRequest, second: str, code: str
) -> None:
    result = run(request_data, ScriptedGenerator([acquire("OPTICAL_IMAGE"), second]))
    assert result.status == "error" and result.stop_reason == code
    assert result.cumulative_cost == 2 and result.accessed_modalities == [M.OPTICAL_IMAGE]
    assert result.turns[-1].generation.text == second
    with pytest.raises(ValueError):
        answer_messages(result, "question")


def test_cumulative_budget(request_data: InputSelectionRequest) -> None:
    request_data.constraints.maximum_total_cost = 3
    result = run(request_data, ScriptedGenerator([acquire("OPTICAL_IMAGE"), acquire("TOPOGRAPHY")]))
    assert result.status == "error" and result.stop_reason == "CUMULATIVE_BUDGET_EXCEEDED"
    assert result.cumulative_cost == 2


@pytest.mark.parametrize(
    "availability", [AssetAvailability.UNAVAILABLE, AssetAvailability.CASE_SPECIFIC]
)
def test_unavailable(request_data: InputSelectionRequest, availability: AssetAvailability) -> None:
    request_data.assets[1].availability = availability
    result = run(request_data, ScriptedGenerator([acquire("OPTICAL_IMAGE")]))
    assert result.stop_reason == "ASSET_NOT_AVAILABLE" and result.cumulative_cost == 0


def test_forbidden(request_data: InputSelectionRequest) -> None:
    request_data.constraints.forbidden_modalities = {M.OPTICAL_IMAGE}
    result = run(request_data, ScriptedGenerator([acquire("OPTICAL_IMAGE")]))
    assert result.stop_reason == "MODALITY_FORBIDDEN"


def test_required_completion_and_finish(request_data: InputSelectionRequest) -> None:
    request_data.constraints.required_modalities = {M.CRATER_CATALOG, M.TOPOGRAPHY}
    result = run(request_data, ScriptedGenerator([acquire("OPTICAL_IMAGE")]))
    assert result.stop_reason == "REQUIRED_COMPLETION_INFEASIBLE"
    assert run(request_data, ScriptedGenerator([STOP])).stop_reason == "REQUIRED_MODALITIES_MISSING"
    result = run(
        request_data, ScriptedGenerator([acquire("CRATER_CATALOG"), acquire("TOPOGRAPHY")])
    )
    assert result.status == "ready" and result.cumulative_cost == 3
    request_data.constraints.maximum_total_cost = 2
    generator = ScriptedGenerator([])
    assert run(request_data, generator).stop_reason == "NO_FEASIBLE_COMPLETION"
    assert not generator.messages


@pytest.mark.parametrize(
    "budget,count,reason", [(2, 2, "NO_FEASIBLE_ADDITIONAL_MODALITY"), (4, 1, "ACQUISITION_LIMIT")]
)
def test_system_stop(
    request_data: InputSelectionRequest, budget: int, count: int, reason: str
) -> None:
    request_data.constraints.maximum_total_cost = budget
    request_data.constraints.maximum_modalities = count
    generator = ScriptedGenerator([acquire("OPTICAL_IMAGE")])
    result = run(request_data, generator)
    assert result.status == "ready" and result.stop_reason == reason
    assert result.stop_actor == "system" and len(generator.messages) == 1


@pytest.mark.parametrize("finish", ["length", "unknown"])
def test_selector_truncation(request_data: InputSelectionRequest, finish: str) -> None:
    result = run(request_data, ScriptedGenerator([STOP], finish))
    assert result.status == "error" and result.stop_reason == "SELECTOR_TRUNCATED_OR_UNVERIFIED"


def test_load_failure_is_not_refunded(request_data: InputSelectionRequest) -> None:
    def fail(modality: M) -> EvidenceObservation:
        raise OSError("fixture missing")

    result = run_iterative_selection(
        request_data,
        POLICY,
        ScriptedGenerator([acquire("TOPOGRAPHY")]),
        fail,
        model_id="fixture",
        execution_kind="test",
    )
    assert result.status == "error" and result.cumulative_cost == 2
    assert result.stop_reason == "EVIDENCE_LOAD_ERROR"
    assert result.turns[0].observation is None


@pytest.mark.parametrize(
    "change",
    [
        {"action": "FINISH", "reason": "x", "modality": "TOPOGRAPHY"},
        {"action": "REQUEST_MODALITY", "reason": "x"},
        {"action": "FINISH", "reason": " "},
        {"action": "FINISH", "reason": "x", "extra": True},
    ],
)
def test_invalid_action(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentAction.model_validate(change)
    with pytest.raises(ValidationError):
        CompactAgentAction.model_validate(change)


@pytest.mark.parametrize(
    "finish,status", [("eos", "success"), ("length", "truncated"), ("unknown", "unverified")]
)
def test_answer_status_and_persistence(
    request_data: InputSelectionRequest, tmp_path: Path, finish: str, status: str
) -> None:
    selection = run(request_data, ScriptedGenerator([acquire("CRATER_CATALOG"), STOP]))
    result = run_iterative_answer(
        selection,
        "Shared prompt",
        ScriptedGenerator(["Fixture answer"], finish),
        max_new_tokens=100,
    )
    assert result.status == status
    assert IterativeAnswer.model_validate_json(result.model_dump_json()) == result
    destination = tmp_path / "new-run" / "Q1__AGENT_ITERATIVE.json"
    save_iterative_answer(result, destination)
    assert IterativeAnswer.model_validate_json(destination.read_text()) == result
    with pytest.raises(FileExistsError):
        save_iterative_answer(result, destination)
    with pytest.raises(ValueError, match="raw"):
        save_iterative_answer(result, tmp_path / "raw" / "result.json")


def test_invalid_trace_cost(request_data: InputSelectionRequest) -> None:
    selection = run(request_data, ScriptedGenerator([STOP]))
    payload = selection.model_dump(mode="json")
    payload["cumulative_cost"] = 100
    with pytest.raises(ValidationError):
        IterativeSelection.model_validate(payload)


def test_explicit_budget_and_token_units(request_data: InputSelectionRequest) -> None:
    request_data.constraints.maximum_total_cost = None
    with pytest.raises(ValueError, match="explicit"):
        run(request_data, ScriptedGenerator([]))
    request_data.constraints.maximum_total_cost = 4
    request_data.assets[0].estimated_cost = 1.5
    with pytest.raises(ValueError, match="integer"):
        run_iterative_selection(
            request_data,
            IterativePolicy(cost_unit="input_tokens", cost_definition="fixture"),
            ScriptedGenerator([]),
            fixture_observation,
            model_id="fixture",
            execution_kind="test",
        )
