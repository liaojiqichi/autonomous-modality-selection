"""Final-proposal protocol and reproducible paired draws."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_modality.experiments import scenario_seed
from autonomous_modality.protocol import ExperimentProtocol


def test_protocol_round_trip_and_record_count() -> None:
    protocol = ExperimentProtocol.model_validate_json(
        Path("configs/experiment_protocol.json").read_text(encoding="utf-8")
    )
    assert ExperimentProtocol.model_validate_json(protocol.model_dump_json()) == protocol
    assert (
        protocol.held_out_target_count
        * protocol.question_count
        * (3 + protocol.random_draws)
        * len(protocol.models)
        == 1920
    )


@pytest.mark.parametrize(
    "change",
    [
        {"random_draws": 1},
        {"maximum_modalities": 3},
        {"dimensions": ["A", "P", "C"]},
        {"answer_decoding": "sampling"},
    ],
)
def test_protocol_rejects_drift(change: dict[str, object]) -> None:
    protocol = ExperimentProtocol.model_validate_json(
        Path("configs/experiment_protocol.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ValidationError):
        ExperimentProtocol.model_validate({**protocol.model_dump(), **change})


def test_seed_is_stable_and_changes_by_scenario_draw_budget() -> None:
    seed = scenario_seed(42, "fixture-Q1", 4, 0)
    assert seed == scenario_seed(42, "fixture-Q1", 4.0, 0)
    assert len({scenario_seed(42, "fixture-Q1", 4, i) for i in range(5)}) == 5
    assert seed != scenario_seed(42, "fixture-Q2", 4, 0)
    assert seed != scenario_seed(42, "fixture-Q1", 3, 0)
