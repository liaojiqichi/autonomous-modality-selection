"""Target split validation without real planetary data."""

import pytest
from pydantic import ValidationError

from autonomous_modality.dataset import TargetSplit


def split_payload() -> dict[str, object]:
    """Provide invented IDs only."""
    return dict(
        reviewer="fixture",
        development_ids=list(range(1, 7)),
        held_out_ids=list(range(7, 37)),
        inspected_ids=[1, 2],
        approved=True,
    )


def test_valid_split_roundtrip() -> None:
    split = TargetSplit.model_validate(split_payload())
    assert TargetSplit.model_validate_json(split.model_dump_json()) == split


@pytest.mark.parametrize(
    "change",
    [
        {"held_out_ids": [7] * 30},
        {"inspected_ids": [10]},
        {"approved": False},
        {"development_ids": [1, 2]},
        {"held_out_ids": list(range(6, 36))},
    ],
)
def test_invalid_splits(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TargetSplit.model_validate({**split_payload(), **change})
