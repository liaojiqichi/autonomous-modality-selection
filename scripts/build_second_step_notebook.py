"""Create a second-step sufficiency ablation from a supplied working notebook."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import pprint
import sys
import textwrap
from pathlib import Path
from typing import Any

DESTINATION = "notebooks/autonomous_modality_selection_three_target_second_step_dev.ipynb"
PROMPT = (
    "Review the acquired evidence against the question and answer requirements. "
    "Is it sufficient for concrete analytical approaches and feature-grounded explanations? "
    "Identify an unresolved issue using a specific observation or representation limitation. "
    "Compare stopping with each remaining feasible modality: would it address that issue, "
    "enable a distinct analysis, or help distinguish explanations, rather than repeat support? "
    "Request the clearest expected contribution, or FINISH if further acquisition is unlikely "
    "to help within budget. Judge unaccessed evidence only by declared capabilities. "
    "Previously accessed data remain charged; no replacement or refund. "
    "Keep the existing action JSON schema and reason-length limit; briefly justify the action."
)
WRAPPER = '''def selector_generate_reply(messages: list[dict], max_new_tokens: int = 512) -> str:
    """Add the reminder only after one verified acquisition; log effective messages."""
    if SELECTOR_VARIANT != "previous":
        raise ValueError("The second-step ablation requires the previous selector.")
    actual = copy.deepcopy(messages)
    if SECOND_STEP_REVIEW_ENABLED:
        if len(actual) != 2 or actual[0].get("role") != "system" or actual[1].get("role") != "user":
            raise ValueError("Unexpected iterative message structure.")
        payload = json.loads(actual[1]["content"][0]["text"])
        accessed = payload.get("accessed_modalities")
        if not isinstance(accessed, list) or any(not isinstance(m, str) for m in accessed):
            raise ValueError("Invalid acquisition state.")
        if len(accessed) > 1:
            raise ValueError("Unexpected selector call after the acquisition limit.")
        if len(accessed) == 1:
            if not any(b.get("type") == "text" and b.get("text", "").startswith(
                "Acquired evidence: "
            ) for b in actual[1]["content"][1:]):
                raise ValueError("Acquired evidence is missing from the observation context.")
            actual[0]["content"].append({"type": "text", "text": SECOND_STEP_REVIEW_PROMPT})
    return generate_reply(actual, max_new_tokens=max_new_tokens)


'''


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Notebook template changed: {old[:60]}")
    return source.replace(old, new, 1)


def build_notebook(original: dict[str, Any]) -> dict[str, Any]:
    """Preserve all unrelated cells and embedded execution blocks."""
    result = copy.deepcopy(original)
    changed = set()
    for i, cell in enumerate(result["cells"]):
        s = "".join(cell["source"])
        if cell["cell_type"] == "code" and "TARGET_IDS = [16604" in s:
            s = replace_once(
                s,
                'SELECTOR_VARIANT = "previous"  # @param ["updated", "previous"]',
                'SELECTOR_VARIANT = "previous"  # Fixed for this ablation.\n'
                'SECOND_STEP_REVIEW_ENABLED = True  # @param {type:"boolean"}\n'
                "SECOND_STEP_REVIEW_PROMPT = (\n"
                + "\n".join(
                    f"    {line!r}" for line in textwrap.wrap(PROMPT, 82, drop_whitespace=False)
                )
                + "\n)",
            )
            s = replace_once(
                s,
                'RUN_LABEL = "three-target-v2-unified-descriptions-001"  '
                "# New label for changed settings.",
                'RUN_LABEL = ("three-target-v2-second-step-unified-review-001" '
                "if SECOND_STEP_REVIEW_ENABLED\n"
                '             else "three-target-v2-second-step-unified-control-001")',
            )
            s = replace_once(
                s,
                'if SELECTOR_VARIANT not in {"updated", "previous"}:',
                "if type(SECOND_STEP_REVIEW_ENABLED) is not bool:\n"
                '    raise ValueError("SECOND_STEP_REVIEW_ENABLED must be boolean.")\n'
                'if SELECTOR_VARIANT != "previous":',
            )
            changed.add(i)
        elif s.startswith("EXECUTION_SOURCES ="):
            blocks = ast.literal_eval(ast.parse(s).body[0].value)
            old = blocks["iterative"]
            tail = old.index("from autonomous_modality.iterative import (")
            blocks["iterative"] = WRAPPER + old[tail:]
            blocks["target_setup"] = replace_once(
                blocks["target_setup"],
                '    "development_revision": "three-target-v2-updated-selector-1.0",',
                '    "development_revision": "second-step-sufficiency-1.0",\n'
                '    "second_step_review_enabled": SECOND_STEP_REVIEW_ENABLED,\n'
                '    "second_step_review_version": "observation-sufficiency-1.0",\n'
                '    "second_step_review_prompt": SECOND_STEP_REVIEW_PROMPT,\n'
                '    "second_step_review_trigger": "one_acquired_modality_with_observation",',
            )
            s = "EXECUTION_SOURCES = " + pprint.pformat(blocks, width=88, sort_dicts=False) + "\n"
            changed.add(i)
        if i in changed:
            cell["source"] = s.splitlines(keepends=True)
        if cell["cell_type"] == "code":
            cell["outputs"], cell["execution_count"] = [], None
    if len(changed) != 2:
        raise ValueError("Expected exactly the controls and embedded-interface cells.")
    result["cells"][0]["source"] = [
        "# Three-target second-step sufficiency development test\n\n",
        "Based on the supplied working notebook. V2 questions, previous selector, original asset ",
        "descriptions, dependencies, generation and answer routing are preserved. Only the ",
        "iterative decision after one acquired observation receives a sufficiency/next-modality ",
        "reminder. The first decision and one-shot AGENT are unchanged.\n\n",
        "Default SECOND_STEP_REVIEW_ENABLED=True. False runs the unmodified-message control ",
        "with a different label. Each run preserves the three-target/108-record workflow. ",
        "Use a fresh runtime and an unused run label. If comparing runtimes, retain the same ",
        "model revision, code revision and package versions. No additional model calls or ",
        "acquisitions are added. Results are versioned development data; "
        "do not mix with formal runs.\n",
    ]
    result["metadata"].pop("widgets", None)
    result["metadata"]["second_step_ablation"] = {
        "version": "1.0",
        "source_sha256": hashlib.sha256(
            json.dumps(original, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "unchanged_cell_sha256": {
            str(i): cell_digest(c)
            for i, c in enumerate(original["cells"])
            if i not in changed | {0}
        },
    }
    return result


def cell_digest(cell: dict[str, Any]) -> str:
    """Ignore Python formatting while preserving executable statements and literals."""
    source = "".join(cell["source"])
    if cell["cell_type"] == "code" and not any(
        line.startswith(("%", "!")) for line in source.splitlines()
    ):
        source = ast.dump(ast.parse(source), include_attributes=False)
    return hashlib.sha256(source.encode()).hexdigest()


if __name__ == "__main__":
    original = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    body = json.dumps(build_notebook(original), ensure_ascii=False, indent=1)
    print("*** Begin Patch\n*** Add File: " + DESTINATION)
    print("\n".join("+" + line for line in body.splitlines()))
    print("*** End Patch")
