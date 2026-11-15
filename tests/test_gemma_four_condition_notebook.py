"""Offline coverage checks for the Gemma four-condition batch notebook."""

import ast
import json
from pathlib import Path


def test_gemma_batch_counts_only_the_four_requested_conditions(tmp_path: Path) -> None:
    notebook = Path(__file__).parents[1] / "notebooks/gemma_heldout_four_conditions.ipynb"
    cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
    sources = ["".join(cell["source"]) for cell in cells if cell["cell_type"] == "code"]
    for source in sources:
        compile(source, str(notebook), "exec")
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "").endswith(
                "_SOURCE"
            ):
                compile(ast.literal_eval(node.value), str(notebook), "exec")
    assert "run_target_revisions" not in "\n".join(sources)
    folder = tmp_path / "run" / "gemma4-e4b" / "crater-1" / "budget-4"
    folder.mkdir(parents=True)
    for condition in ("AGENT", "AGENT_ANSWER_REVISION"):
        (folder / f"Q1__{condition}__r01.json").write_text('{"status":"success"}')
    scope = dict(
        RESULTS_ROOT=tmp_path,
        RUN_LABEL="run",
        MODEL_TAG="gemma4-e4b",
        BUDGET=4,
        BATCH_NUMBER=1,
        BATCH_TARGET_IDS=[1],
        json=json,
    )
    exec(sources[-1], scope)
    assert scope["statuses"] == {"missing": 31, "success": 1}
