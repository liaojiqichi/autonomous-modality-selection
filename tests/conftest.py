"""Shared fixtures for the input-modality selection tests."""

import pytest

from autonomous_modality.cli import mercury_demo_assets
from autonomous_modality.models import (
    CraterQuestion,
    CraterQuestionType,
    CraterReference,
    DataAssetProfile,
    InputDataModality,
    InputSelectionConstraints,
    InputSelectionRequest,
)


@pytest.fixture
def selection_request() -> InputSelectionRequest:
    """Return a representative Mercury crater selection request."""
    return InputSelectionRequest(
        question=CraterQuestion(
            question_id="caloris-approaches",
            crater=CraterReference(
                name="Caloris",
                latitude=30.5,
                longitude=162.7,
                diameter_km=1550.0,
            ),
            text="Which analytical approaches could investigate Caloris formation?",
            question_type=CraterQuestionType.ANALYTICAL_APPROACH_DISCOVERY,
        ),
        assets=mercury_demo_assets(),
        constraints=InputSelectionConstraints(maximum_modalities=3),
    )


@pytest.fixture
def budget_trap_request() -> InputSelectionRequest:
    """Metadata-only fixture with a feasible pair that greedy selection misses."""
    return InputSelectionRequest(
        question=CraterQuestion(
            question_id="budget-trap-fixture",
            text="Metadata-only cross-modal selection test, not an observed result.",
            question_type=CraterQuestionType.CROSS_MODAL_RELATIONSHIP_DISCOVERY,
        ),
        assets=[
            DataAssetProfile(
                asset_id=f"fixture-{modality.value}",
                title="Metadata-only test fixture",
                modality=modality,
                estimated_cost=cost,
                limitations=["Metadata-only fixture; no scientific data loaded or verified."],
            )
            for modality, cost in (
                (InputDataModality.TOPOGRAPHY, 2.0),
                (InputDataModality.OPTICAL_IMAGE, 1.0),
                (InputDataModality.CRATER_CATALOG, 1.0),
            )
        ],
        constraints=InputSelectionConstraints(maximum_modalities=2, maximum_total_cost=2.0),
    )
