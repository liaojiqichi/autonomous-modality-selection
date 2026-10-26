"""Check the retained original-selector entry point uses shared declarations."""

import ast
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / "scripts/build_optical_description_notebook.py"))


def test_notebook_uses_current_descriptions_and_compiles() -> None:
    notebook = json.loads((ROOT / BUILDER["DESTINATION"]).read_text(encoding="utf-8"))
    assert notebook == BUILDER["build_notebook"]()
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        assert cell["outputs"] == [] and cell["execution_count"] is None
        source = "".join(cell["source"])
        if not any(line.startswith(("%", "!")) for line in source.splitlines()):
            compile(source, "cell", "exec")
        if source.startswith("EXECUTION_SOURCES ="):
            blocks = ast.literal_eval(ast.parse(source).body[0].value)
            assert "ASSETS = describe_assets(" in blocks["target_setup"]
            assert "OPTICAL_DESCRIPTION_VARIANT" not in blocks["target_setup"]
            for block in blocks.values():
                compile(block, "embedded", "exec")
        if "TARGET_IDS = [16604" in source:
            namespace = {}
            exec(source, namespace)
            assert namespace["SELECTOR_VARIANT"] == "previous"
            assert namespace["TARGET_IDS"] == [16604, 5031, 2179]
