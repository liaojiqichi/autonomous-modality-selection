"""Offline metadata fixtures; no real planetary data or network access."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_modality.heldout import (
    EXCLUDED_IDS,
    Cohort,
    prepare,
    select_cohort,
    write_new,
)
from autonomous_modality.pilot import CatalogueRow


def rows() -> list[CatalogueRow]:
    return [
        CatalogueRow(
            id=30000 + i,
            lat_n=10.0,
            lon_e_0=40.0,
            diameter=70.0,
            name=f"Fixture {i}",
            int_shp="x",
            rim_shp="x",
            cent_struc="x",
            rayed="n",
        )
        for i in range(45)
    ]


def test_sampling_is_order_independent_and_serializable() -> None:
    result = select_cohort(rows(), "a" * 64)
    assert result == select_cohort(list(reversed(rows())), "a" * 64)
    assert len(result.targets) == 30 and len(result.reserves) == 15
    assert Cohort.model_validate_json(result.model_dump_json()) == result
    assert not result.ready_for_evaluation and not result.llm_called


def test_seed_changes_allocation() -> None:
    assert select_cohort(rows(), "a" * 64, 1).targets != select_cohort(rows(), "a" * 64, 2).targets


def test_all_historical_cases_excluded_including_holds() -> None:
    historical = [rows()[0].model_copy(update={"id": i}) for i in EXCLUDED_IDS]
    assert select_cohort(rows() + historical, "a" * 64) == select_cohort(rows(), "a" * 64)


@pytest.mark.parametrize(
    "change",
    [
        {"name": " "},
        {"diameter": 49.9},
        {"diameter": 150.1},
        {"lat_n": 45.0},
        {"lat_n": -45.0},
        {"lon_e_0": 15.0},
        {"lon_e_0": -150.0},
    ],
)
def test_geographic_and_size_exclusions(change: dict[str, object]) -> None:
    invalid = rows()[0].model_copy(update={"id": 99999, **change})
    assert select_cohort([*rows(), invalid], "a" * 64) == select_cohort(rows(), "a" * 64)


def test_insufficient_and_duplicate_pools_rejected() -> None:
    with pytest.raises(ValidationError):
        select_cohort(rows()[:29], "a" * 64)
    with pytest.raises(ValueError, match="DUPLICATE"):
        select_cohort([*rows(), rows()[0]], "a" * 64)


def test_corrupt_cohort_rejected() -> None:
    payload = select_cohort(rows(), "a" * 64).model_dump(mode="json")
    payload["reserves"][0] = payload["targets"][0]
    with pytest.raises(ValidationError, match="DUPLICATE"):
        Cohort.model_validate(payload)


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        prepare(tmp_path / "missing", tmp_path / "missing", tmp_path)
    destination = tmp_path / "cohort.json"
    cohort = select_cohort(rows(), "a" * 64)
    write_new(destination, cohort)
    before = destination.read_bytes()
    with pytest.raises(FileExistsError):
        write_new(destination, cohort)
    assert destination.read_bytes() == before
