"""Synthetic metadata-only checks for the frozen four-modality design."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_modality.benchmark import QuestionSet, QuestionSpec
from autonomous_modality.heldout import Cohort, select_cohort
from autonomous_modality.heldout_protocol import FrozenProtocol, freeze_design, options
from autonomous_modality.heldout_release import complete_spectral
from autonomous_modality.models import CraterQuestionType
from autonomous_modality.multispectral_acquisition import Tile, intersects
from autonomous_modality.pilot import CatalogueRow


def fixture_cohort() -> Cohort:
    return select_cohort(
        [
            CatalogueRow(
                id=40000 + i,
                name=f"Fixture {i}",
                lat_n=1.0,
                lon_e_0=50.0,
                diameter=80.0,
                int_shp="x",
                rim_shp="x",
                cent_struc="x",
                rayed="n",
            )
            for i in range(35)
        ],
        "a" * 64,
    )


def test_shared_design_reproducible_and_balanced() -> None:
    questions = QuestionSet(
        questions=[
            QuestionSpec(
                question_id=f"Q{i}",
                text="Investigate {crater}",
                answer_requirements=["Use evidence"],
                question_type=CraterQuestionType.ANALYTICAL_APPROACH_DISCOVERY,
            )
            for i in range(1, 5)
        ]
    )
    design = freeze_design(fixture_cohort(), questions)
    assert design == freeze_design(fixture_cohort(), questions)
    assert len(design.scenarios) == 120 and len(design.human_review_slots) == 64
    for item in design.scenarios:
        assert len(item.random_budget_3) == len(item.random_budget_4) == 5
        assert all(choice in options(3) for choice in item.random_budget_3)
        assert all(choice in options(4) for choice in item.random_budget_4)
    assert len(options(4)) == 10 and len(options(3)) == 7
    keys = [(s.model, s.condition, s.question_id, s.case_id) for s in design.human_review_slots]
    assert len(set(keys)) == 64


@pytest.mark.parametrize(
    "change",
    [
        {"cost_unit": "input_tokens"},
        {"costs": {}},
        {"models": ("other",)},
        {"runtime_approved": True},
        {"image_edge": 320},
        {"primary_conditions": ("AGENT",)},
    ],
)
def test_protocol_rejects_unversioned_changes(change: dict) -> None:
    with pytest.raises(ValidationError):
        FrozenProtocol(question_sha256="a" * 64, cohort_sha256="b" * 64, pinned_files={}, **change)


@pytest.mark.parametrize(
    "west,east,bounds,expected",
    [
        (180.0, -143.991145, [-155.0, -2.0, -142.0, 10.0], True),
        (180.0, -143.991145, [205.0, 1.0, 215.0, 10.0], True),
        (144.0, -179.991145, [170.0, 1.0, -175.0, 10.0], True),
        (180.0, -143.991145, [-100.0, 1.0, -90.0, 10.0], False),
        (108.0, 144.008855, [111.0, 1.0, 117.0, 10.0], True),
        (180.0, -143.991145, [-155.0, 30.0, -142.0, 40.0], False),
    ],
)
def test_signed_wraparound_tile_matching(
    west: float, east: float, bounds: list[float], expected: bool
) -> None:
    tile = Tile(
        product_id="MDIS_MDR_064PPD_H08NE4",
        label_path="fixture",
        label_sha256="a" * 64,
        url="https://example.invalid",
        expected_bytes=1,
        west=west,
        east=east,
        south=0.0,
        north=22.5,
    )
    assert intersects(bounds, tile) is expected


def test_reuse_refuses_existing_output(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        complete_spectral(tmp_path, tmp_path, tmp_path, tmp_path, tmp_path)


def test_invalid_budget_rejected() -> None:
    with pytest.raises(ValueError):
        options(5)
