"""Check missing-file and wrong-record handling without running inference."""

import json
from collections import Counter
from pathlib import Path

import pytest


def test_qwen_batch_inspection_rejects_misfiled_records(tmp_path: Path) -> None:
    path = Path(__file__).parents[1] / "notebooks/qwen_heldout_four_conditions.ipynb"
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    scope = dict(
        Counter=Counter,
        json=json,
        BATCHES=[[1]],
        BATCH_NUMBER=1,
        RESULTS_ROOT=tmp_path,
        RUN_LABEL="test",
        MODEL_TAG="qwen",
        MODEL_ID="Qwen",
        BUDGET=4,
    )
    exec("".join(cells[2]["source"]), scope)
    assert scope["inspect_batch"]() == {"missing": 32}
    folder = tmp_path / "test/qwen/crater-1/budget-4"
    folder.mkdir(parents=True)
    (folder / "Q1__AGENT__r01.json").write_text(
        json.dumps(
            dict(
                model="Qwen",
                case_id="2",
                question_id="Q1",
                condition="AGENT",
                draw_index=0,
                status="success",
            )
        )
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        scope["inspect_batch"]()
