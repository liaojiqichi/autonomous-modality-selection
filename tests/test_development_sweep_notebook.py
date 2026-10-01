"""Exercise the sweep adapter against actual notebook routing with scripted replies."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from test_colab_notebook import notebook_runtime as notebook_runtime


def adapter() -> ModuleType:
    """Load definitions only; this example has no top-level inference."""
    spec = importlib.util.spec_from_file_location(
        "sweep_example", Path("examples/colab_development_sweep.py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_fixture(namespace: dict[str, Any]) -> dict[str, Any]:
    """Supply synthetic runtime metadata and a complete fixture receipt."""
    namespace.update(
        CONFIG={"split": "development", "cost_unit": "legacy_ordinal_units", "model": "FIXTURE"},
        model=SimpleNamespace(
            config=SimpleNamespace(to_dict=lambda: {"_name_or_path": "FIXTURE"}),
            generation_config=SimpleNamespace(to_dict=lambda: {}),
        ),
        processor=SimpleNamespace(),
    )
    receipt = {
        "source_sha256": namespace["SOURCE_HASHES"],
        "output_sha256": namespace["receipt"].output_sha256,
    }
    namespace["receipt_path"].write_text(json.dumps(receipt), encoding="utf-8")
    return namespace


def test_actual_notebook_adapter_and_resume(
    notebook_runtime: dict[str, Any], tmp_path: Path
) -> None:
    ns = setup_fixture(notebook_runtime)
    module = adapter()
    plan = module.prepare_from_notebook(ns, execution_kind="test")
    assert not ns["GENERATION_LOG"]
    assert len(plan.scenarios) == 4
    out = tmp_path / "sweep"
    records = module.run_from_notebook(ns, out, execution_kind="test")
    assert len(records) == 32 and all(r.status == "success" for r in records)
    assert all(r.execution_kind == "test" for r in records)
    for r in records:
        assert "FIXTURE_SELECTOR_SECRET" not in json.dumps(r.messages)
        assert r.generation.text == "TEST ANSWER; NOT A SCIENTIFIC OBSERVATION"
    module.run_from_notebook(ns, out, execution_kind="test")
    assert len(ns["GENERATION_LOG"]) == 32
    ns["ANSWER_TOKENS"] += 1
    with pytest.raises(ValueError, match="configuration changed"):
        module.run_from_notebook(ns, out, execution_kind="test")


@pytest.mark.parametrize("change", ["terrain", "catalogue", "held_out", "source", "view"])
def test_adapter_rejects_stale_inputs(notebook_runtime: dict[str, Any], change: str) -> None:
    ns = setup_fixture(notebook_runtime)
    if change == "terrain":
        ns["TERRAIN_TEXT"] = "CHANGED"
    elif change == "catalogue":
        ns["CATALOGUE_TEXT"] = "{}"
    elif change == "held_out":
        ns["CONFIG"]["split"] = "held_out"
    elif change == "source":
        ns["SOURCES"]["catalogue.json"].write_text("CHANGED", encoding="utf-8")
    else:
        ns["PREVIEWS"]["elevation"].write_bytes(b"CHANGED")
    with pytest.raises(ValueError):
        adapter().prepare_from_notebook(ns, execution_kind="test")
    assert ns["GENERATION_LOG"] == []
