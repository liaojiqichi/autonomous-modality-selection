"""Review completeness tests use invented records only."""

import pytest
from pydantic import ValidationError

from autonomous_modality.multispectral_release import Review, Reviews, validate_reviews


def review(case_id: int) -> Review:
    return Review(
        case_id=case_id,
        status="provisional_pass",
        observation="Synthetic test review",
        limitations="No actual scientific data",
    )


def test_complete_reviews() -> None:
    validate_reviews(Reviews(reviewer="Test", reviews=[review(1), review(2)]), [1, 2])


@pytest.mark.parametrize("ids", [[1], [1, 1], [1, 3]])
def test_missing_duplicate_or_wrong_target(ids: list[int]) -> None:
    with pytest.raises(ValueError, match="TARGET_SET_MISMATCH"):
        validate_reviews(Reviews(reviewer="Test", reviews=[review(i) for i in ids]), [1, 2])


def test_hold_cannot_be_released() -> None:
    record = review(1)
    record.status = "hold"
    with pytest.raises(ValueError, match="HOLD"):
        validate_reviews(Reviews(reviewer="Test", reviews=[record]), [1])


def test_empty_observations_rejected() -> None:
    with pytest.raises(ValidationError):
        Review(case_id=1, status="provisional_pass", observation=" ", limitations="Test")
