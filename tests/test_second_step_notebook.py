"""Offline tests of the observation-only reminder and preserved notebook cells."""

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

PATH = (
    Path(__file__).resolve().parents[1]
    / "notebooks/autonomous_modality_selection_three_target_second_step_dev.ipynb"
)


def notebook() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def blocks() -> dict:
    s = next(
        "".join(c["source"])
        for c in notebook()["cells"]
        if "".join(c["source"]).startswith("EXECUTION_SOURCES =")
    )
    return ast.literal_eval(ast.parse(s).body[0].value)


def test_clean_compiles_and_unchanged_cells() -> None:
    n = notebook()
    for i, digest in n["metadata"]["second_step_ablation"]["unchanged_cell_sha256"].items():
        cell = n["cells"][int(i)]
        source = "".join(cell["source"])
        if cell["cell_type"] == "code" and not any(
            line.startswith(("%", "!")) for line in source.splitlines()
        ):
            source = ast.dump(ast.parse(source), include_attributes=False)
        assert hashlib.sha256(source.encode()).hexdigest() == digest
    for c in n["cells"]:
        if c["cell_type"] == "code":
            assert c["outputs"] == [] and c["execution_count"] is None
            s = "".join(c["source"])
            if not any(line.startswith(("%", "!")) for line in s.splitlines()):
                compile(s, "cell", "exec")
    for s in blocks().values():
        compile(s, "embedded", "exec")


@pytest.mark.parametrize(
    "enabled,accessed,reminder",
    [
        (True, [], False),
        (True, ["TOPOGRAPHY"], True),
        (False, [], False),
        (False, ["TOPOGRAPHY"], False),
    ],
)
def test_reminder_only_after_observation(
    enabled: bool, accessed: list[str], reminder: bool
) -> None:
    tree = ast.parse(blocks()["iterative"]).body[0]
    calls = []

    def generate(messages: list[dict], max_new_tokens: int) -> str:
        calls.append((messages, max_new_tokens))
        return "fixture"

    ns = dict(
        copy=copy,
        json=json,
        SELECTOR_VARIANT="previous",
        SECOND_STEP_REVIEW_ENABLED=enabled,
        SECOND_STEP_REVIEW_PROMPT="review",
        generate_reply=generate,
    )
    exec(compile(ast.Module(body=[tree], type_ignores=[]), "wrapper", "exec"), ns)
    content = [{"type": "text", "text": json.dumps({"accessed_modalities": accessed})}]
    if accessed:
        content += [
            {"type": "text", "text": "Acquired evidence: TOPOGRAPHY"},
            {"type": "text", "text": "fixture observation"},
        ]
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "old rules"}]},
        {"role": "user", "content": content},
    ]
    original = copy.deepcopy(messages)
    assert ns["selector_generate_reply"](messages, 512) == "fixture"
    assert messages == original
    assert len(calls) == 1 and calls[0][1] == 512
    assert calls[0][0][1] == original[1]
    assert len(calls[0][0][0]["content"]) == 1 + int(reminder)
    if not reminder:
        assert calls[0][0] == original


@pytest.mark.parametrize("accessed", [None, "TOPOGRAPHY", [17], ["X", "Y"], ["X"]])
def test_invalid_or_missing_observation_is_rejected(accessed: object) -> None:
    fn = ast.parse(blocks()["iterative"]).body[0]
    ns = dict(copy=copy, json=json, SELECTOR_VARIANT="previous", SECOND_STEP_REVIEW_ENABLED=True)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "wrapper", "exec"), ns)
    messages = [
        {"role": "system", "content": []},
        {
            "role": "user",
            "content": [{"type": "text", "text": json.dumps({"accessed_modalities": accessed})}],
        },
    ]
    with pytest.raises(ValueError):
        ns["selector_generate_reply"](messages)


def test_prompt_never_routes_to_answer_or_one_shot() -> None:
    b = blocks()
    assert "SECOND_STEP" not in b["answer"] and "SECOND_STEP" not in b["selector"]
    assert '"second_step_review_trigger"' in b["target_setup"]
    assert "selector_generate_reply," in b["experiment"]
