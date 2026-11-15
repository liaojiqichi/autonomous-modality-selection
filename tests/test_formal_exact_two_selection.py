"""Pair-only formal selectors, tested without inference or scientific data."""

import ast
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]


def selector_source(notebook: str) -> str:
    cells = json.loads((ROOT / "notebooks" / notebook).read_text(encoding="utf-8"))["cells"]
    for cell in cells:
        if cell["cell_type"] != "code":
            continue
        for node in ast.walk(ast.parse("".join(cell["source"]))):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "def valid_selection(" in node.value
            ):
                return node.value
    raise AssertionError("Selector not found")


@pytest.fixture(
    params=["qwen_heldout_four_conditions.ipynb", "gemma_heldout_four_conditions.ipynb"]
)
def scope(request: pytest.FixtureRequest) -> dict[str, Any]:
    ns: dict[str, Any] = {
        "ASSETS": {
            m: {"cost": 1 if m == "CRATER_CATALOG" else 2}
            for m in ("CRATER_CATALOG", "MULTISPECTRAL_IMAGE", "OPTICAL_IMAGE", "TOPOGRAPHY")
        },
        "BUDGET": 4,
        "MAX_MODALITIES": 2,
        "CONFIG": {},
        "SEED": 42,
        "CASE_ID": "16604",
        "RANDOM_DRAWS": 5,
        "json": json,
    }
    exec(selector_source(request.param), ns)
    return ns


def test_six_pairs_and_matching_random_draws(scope: dict[str, Any]) -> None:
    assert len(scope["OPTIONS"]) == 6
    assert all(len(o["selected"]) == 2 for o in scope["OPTIONS"].values())
    for i in range(5):
        selected, _ = scope["select_inputs"]("RANDOM", "fixture", "Q1", i)
        assert len(set(selected)) == 2
        assert selected == scope["select_inputs"]("RANDOM", "fixture", "Q1", i)[0]
    assert scope["CONFIG"]["selection_cardinality_version"] == "exact-two-1.0"


@pytest.mark.parametrize(
    "selection",
    [
        [],
        ["CRATER_CATALOG"],
        ["CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY"],
        ["OPTICAL_IMAGE", "OPTICAL_IMAGE"],
        ["OPTICAL_IMAGE", "UNKNOWN"],
    ],
)
def test_invalid_selections_rejected(scope: dict[str, Any], selection: list[str]) -> None:
    with pytest.raises(ValueError):
        scope["valid_selection"](selection)


def test_reference_conditions_keep_their_inputs(scope: dict[str, Any]) -> None:
    assert scope["select_inputs"]("NO_DATA", "fixture", "Q1")[0] == []
    assert len(scope["select_inputs"]("ALL_AVAILABLE", "fixture", "Q1")[0]) == 4


def test_both_notebooks_share_selector() -> None:
    assert selector_source("qwen_heldout_four_conditions.ipynb") == selector_source(
        "gemma_heldout_four_conditions.ipynb"
    )
