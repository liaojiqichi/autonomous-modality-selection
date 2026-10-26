"""Build a separate three-target Colab notebook; print an apply_patch document."""

from __future__ import annotations

import copy
import json
import pprint
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = "notebooks/autonomous_modality_selection_three_target_selector_dev.ipynb"
ALIGNMENT = (
    "Choose inputs for the specific question and its answer requirements. "
    "A means distinct analytical approaches feasible with supplied representations. "
    "P means mechanisms or alternative explanations linked to supplied features. "
    "Compare feasible combinations by their additional contribution to A and P, "
    "including information lost when another modality is omitted. "
    "Optical views support qualitative structure, texture, boundaries and spatial relations. "
    "Terrain supports relief and profile comparisons; multispectral summaries support "
    "regional spectral comparisons; catalogue records support historical classification checks. "
    "Use the inventory to judge actual availability and limitations. "
    "Numerical inputs are not inherently more useful than visual evidence. "
    "Optical brightness does not measure elevation or composition. "
    "No modality is mandatory; spending more receives no separate reward."
)
COMPLEMENTARITY = (
    "After observing the first package, identify what remains unresolved. Request a second "
    "modality when it offers a distinct analytical route or helps distinguish explanations; "
    "otherwise finish. Retain the original action schema and cumulative access limits."
)


def revised_questions() -> dict[str, Any]:
    """Restore the exact historical v2 development questions and requirements."""
    value = json.loads((ROOT / "configs/mercury_selection_questions_v2.json").read_text())
    return {
        "version": "mercury-selection-value-dev-2.0-en",
        "split": "development",
        "questions": value["questions"],
    }


def replace_once(source: str, old: str, new: str) -> str:
    """Reject template drift instead of silently missing a replacement."""
    if source.count(old) != 1:
        raise ValueError(f"Template anchor changed: {old[:80]}")
    return source.replace(old, new, 1)


def cell(source: str, kind: str = "code") -> dict[str, Any]:
    """Create a clean notebook cell."""
    if kind == "code":
        source = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--stdin-filename", "cell.py", "-"],
            input=source,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    value: dict[str, Any] = {
        "cell_type": kind,
        "metadata": {},
        "source": source.strip().splitlines(keepends=True),
    }
    if kind == "code":
        value.update(execution_count=None, outputs=[])
    return value


def build_notebook() -> dict[str, Any]:
    """Build the Colab artifact; never perform local model inference."""
    original = json.loads(
        (ROOT / "notebooks/autonomous_modality_selection_four_modality.ipynb").read_text()
    )

    def source(index: int) -> str:
        return "".join(original["cells"][index]["source"])

    setup = source(13)
    shared_names = (
        "BUDGET",
        "SEED",
        "MAX_MODALITIES",
        "RANDOM_DRAWS",
        "IMAGE_EDGE",
        "ANSWER_TOKENS",
        "SELECTOR_TOKENS",
        "MAX_INPUT_TOKENS",
        "RECORD_VERSION",
        "ANSWER_REPETITION_PENALTY",
        "ITERATIVE_SELECTOR_TOKENS",
        "IS_DEVELOPMENT",
    )
    shared_lines = [
        line
        for line in setup.splitlines()
        if any(line.startswith(name + " = ") for name in shared_names)
    ]
    assert len(shared_lines) == len(shared_names)
    for line in shared_lines:
        setup = replace_once(setup, "\n" + line + "\n", "\n")
    for old in (
        "TARGET_ID = 16604  # Other IDs: 5031, 2179, 858, 4870, 19610, 1851.\n",
        'RESULTS_ROOT = Path("/content/experiment-results")  '
        "# Use a Drive path if Drive is already mounted.\n",
        'RUN_LABEL = "four-modality-unified-descriptions-v2-001"  # Must be unused.\n',
    ):
        setup = replace_once(setup, old, "")
    setup = replace_once(
        setup,
        'question_path = PROJECT / "configs/mercury_selection_questions_v2.json"',
        'question_path = RESULTS_ROOT / RUN_LABEL / "development_questions.json"\n'
        "question_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "if question_path.exists():\n"
        "    if json.loads(question_path.read_text()) != DEVELOPMENT_QUESTIONS:\n"
        '        raise ValueError("Questions changed; use a new RUN_LABEL.")\n'
        "else:\n"
        "    write_new_json(question_path, DEVELOPMENT_QUESTIONS)",
    )
    setup = replace_once(
        setup,
        "SELECTOR_TASK = (",
        'if SELECTOR_VARIANT == "updated":\n'
        "    SELECTOR_ALIGNMENT = DEVELOPMENT_ALIGNMENT\n"
        '    SELECTOR_ALIGNMENT_VERSION = "selector-qualitative-dev-2.0"\n'
        "\nSELECTOR_TASK = (",
    )
    setup = replace_once(
        setup,
        '    "protocol": RECORD_VERSION,',
        '    "protocol": RECORD_VERSION,\n'
        '    "development_revision": "three-target-v2-updated-selector-1.0",\n'
        '    "selector_variant": SELECTOR_VARIANT,\n'
        '    "selector_alignment_version": SELECTOR_ALIGNMENT_VERSION,\n'
        '    "iterative_prompt_extension": '
        '(DEVELOPMENT_ALIGNMENT + " " + DEVELOPMENT_COMPLEMENTARITY)\n'
        '        if SELECTOR_VARIANT == "updated" else "",\n'
        '    "execution_sources_sha256": EXECUTION_SOURCES_SHA256,\n'
        '    "resolved_model_revision": RESOLVED_MODEL_REVISION,\n'
        '    "loaded_attention_config": LOADED_ATTENTION_CONFIG,',
    )
    iterative = '''
def selector_generate_reply(messages: list[dict], max_new_tokens: int = 512) -> str:
    """Extend only selector messages; retain the exact effective messages in logs."""
    actual = copy.deepcopy(messages)
    if SELECTOR_VARIANT == "updated":
        actual[0]["content"].append({
            "type": "text",
            "text": DEVELOPMENT_ALIGNMENT + " " + DEVELOPMENT_COMPLEMENTARITY,
        })
    return generate_reply(actual, max_new_tokens=max_new_tokens)

''' + source(19)
    iterative = replace_once(
        iterative,
        "notebook_generator(generate_reply, GENERATION_LOG)",
        "notebook_generator(selector_generate_reply, GENERATION_LOG)",
    )
    experiment = replace_once(
        source(21),
        "    select_inputs_iterative,\n)",
        "    select_inputs_iterative,\n    selector_generate_reply,\n)",
    )
    blocks = {
        "target_setup": setup,
        "selector": source(16),
        "answer": source(17),
        "iterative": iterative,
        "experiment": experiment,
    }
    install = source(9).replace('"transformers>=5"', '"transformers==5.19.0"')
    before_else, separator, after_else = install.partition("else [")
    assert separator
    install = (
        before_else
        + separator
        + after_else.replace(
            '"accelerate", "bitsandbytes>=0.48,<1"',
            '"accelerate==1.15.0", "bitsandbytes==0.50.2"',
        )
    )
    install = replace_once(
        install,
        "loaded = {",
        'if MODEL_ID == "google/gemma-4-E4B-it":\n'
        '    packages += ["numpy==2.1.3", "rasterio==1.5.2",\n'
        '                 "matplotlib==3.10.0", "pydantic==2.13.5"]\n'
        "loaded = {",
    )
    install = install.replace(
        '("transformers", "accelerate", "bitsandbytes", "Pillow")',
        '("transformers", "accelerate", "bitsandbytes", "Pillow", '
        '"numpy", "rasterio", "matplotlib", "pydantic")',
    )
    install += '\nMODEL_REVISION = "main"  # Set a saved commit SHA to reproduce an earlier load.\n'
    loading = replace_once(
        source(10),
        "    model = model_class.from_pretrained(",
        "    from huggingface_hub import HfApi\n\n"
        "    RESOLVED_MODEL_REVISION = HfApi().model_info(MODEL_ID, revision=MODEL_REVISION).sha\n"
        "    if not RESOLVED_MODEL_REVISION:\n"
        '        raise RuntimeError("Could not resolve a model revision.")\n'
        '    backbone_attention = "sdpa"\n'
        "    model = model_class.from_pretrained(",
    )
    loading = replace_once(
        loading,
        '        attn_implementation="sdpa",',
        "        attn_implementation=backbone_attention,\n"
        "        revision=RESOLVED_MODEL_REVISION,",
    )
    loading = replace_once(
        loading,
        "    processor = AutoProcessor.from_pretrained(MODEL_ID)",
        "    processor = AutoProcessor.from_pretrained(MODEL_ID, revision=RESOLVED_MODEL_REVISION)",
    )
    loading += """
RESOLVED_MODEL_REVISION = globals().get(
    "RESOLVED_MODEL_REVISION", getattr(model.config, "_commit_hash", None)
)
if not RESOLVED_MODEL_REVISION:
    raise RuntimeError("Reused model revision is unknown; load in a fresh runtime.")
LOADED_ATTENTION_CONFIG = {
    name: getattr(getattr(model.config, name), "_attn_implementation", None)
    for name in ("text_config", "vision_config", "audio_config")
    if getattr(model.config, name, None) is not None
}
print("Model and processor revision:", RESOLVED_MODEL_REVISION)
print("Loaded attention:", LOADED_ATTENTION_CONFIG)
"""
    processor_setup = """
image_processor = processor.image_processor
if MODEL_ID == "Qwen/Qwen3-VL-8B-Instruct":
    if not isinstance(getattr(image_processor, "size", None), dict):
        raise RuntimeError("Unexpected Qwen image processor configuration.")
    image_processor.size = {
        **image_processor.size, "shortest_edge": 128 * 128, "longest_edge": 320 * 320,
    }
    if hasattr(image_processor, "min_pixels"):
        image_processor.min_pixels = 128 * 128
    if hasattr(image_processor, "max_pixels"):
        image_processor.max_pixels = 320 * 320
else:
    if not hasattr(image_processor, "max_soft_tokens"):
        raise RuntimeError("Unexpected Gemma image processor configuration.")
    image_processor.max_soft_tokens = 280
print(image_processor.to_json_string())
"""
    controls = """
from pathlib import Path

TARGET_IDS = [16604, 5031, 2179]  # Eminescu, Nampeyo, Thoreau; development only.
SELECTOR_VARIANT = "updated"  # @param ["updated", "previous"]
RUN_LABEL = "three-target-v2-unified-descriptions-001"  # New label for changed settings.
RESULTS_ROOT = Path("/content/experiment-results")  # A mounted Drive path is also supported.

if SELECTOR_VARIANT not in {"updated", "previous"}:
    raise ValueError("Unknown selector variant.")
if TARGET_IDS != [16604, 5031, 2179]:
    raise ValueError("This notebook is restricted to the three development targets.")
if not RUN_LABEL or Path(RUN_LABEL).name != RUN_LABEL:
    raise ValueError("RUN_LABEL must be one directory name.")
print("Expected: 3 targets x 4 questions x 9 attempts = 108 records per model.")
"""
    controls += "\n# Shared settings applied to every target and condition.\n"
    controls += "\n".join(shared_lines) + "\n"
    constants = (
        "DEVELOPMENT_SETTINGS = "
        + pprint.pformat(
            {
                "alignment": ALIGNMENT,
                "complementarity": COMPLEMENTARITY,
                "questions": revised_questions(),
            },
            width=88,
            sort_dicts=False,
        )
        + """
DEVELOPMENT_ALIGNMENT = DEVELOPMENT_SETTINGS["alignment"]
DEVELOPMENT_COMPLEMENTARITY = DEVELOPMENT_SETTINGS["complementarity"]
DEVELOPMENT_QUESTIONS = DEVELOPMENT_SETTINGS["questions"]
"""
    )
    block_cell = "EXECUTION_SOURCES = " + pprint.pformat(blocks, width=88, sort_dicts=False) + "\n"
    runner = """
import gc
import hashlib
import json
from collections import Counter

from IPython import get_ipython

EXECUTION_SOURCES_SHA256 = hashlib.sha256(
    json.dumps(EXECUTION_SOURCES, sort_keys=True).encode("utf-8")
).hexdigest()
run_root = RESULTS_ROOT / RUN_LABEL
run_root.mkdir(parents=True, exist_ok=True)
source_path = run_root / "execution_sources.json"
if source_path.exists():
    if json.loads(source_path.read_text()) != EXECUTION_SOURCES:
        raise ValueError("Execution code changed; use a new RUN_LABEL.")
else:
    with source_path.open("x", encoding="utf-8") as stream:
        json.dump(EXECUTION_SOURCES, stream, indent=2)

shell = get_ipython()
if shell is None:
    raise RuntimeError("Run this notebook in Colab/IPython.")
for TARGET_ID in TARGET_IDS:
    print("Starting development target:", TARGET_ID)
    for stage_name in ("target_setup", "selector", "answer", "iterative", "experiment"):
        # IPython preserves inspectable sources for existing provenance checks.
        execution = shell.run_cell(EXECUTION_SOURCES[stage_name])
        execution.raise_error()
    # The stages above publish these validated objects in the notebook namespace.
    Attempt = globals()["Attempt"]
    OUTPUT = globals()["OUTPUT"]
    CASE_NAME = globals()["CASE_NAME"]
    MODEL_TAG = globals()["MODEL_TAG"]
    target_records = [
        Attempt.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(OUTPUT.glob("Q*__*__r*.json"))
    ]
    if len(target_records) != 36:
        raise RuntimeError(f"Incomplete target {TARGET_ID}: {len(target_records)}/36")
    print(CASE_NAME, "36/36", dict(Counter(r.status for r in target_records)))
    GENERATION_LOG.clear()
    gc.collect()
    torch.cuda.empty_cache()
print("Batch finished. Failed/truncated attempts remain recorded, without retries.")
"""
    summary = """
from collections import Counter

all_records = []
for target in TARGET_IDS:
    folder = RESULTS_ROOT / RUN_LABEL / MODEL_TAG / f"crater-{target}" / f"budget-{BUDGET}"
    values = [Attempt.model_validate_json(p.read_text(encoding="utf-8"))
              for p in sorted(folder.glob("Q*__*__r*.json"))]
    print(target, len(values), "/36", dict(Counter(r.status for r in values)))
    all_records.extend(values)
print("Total:", len(all_records), "/108")
print("Statuses:", dict(Counter(r.status for r in all_records)))
print("Conditions:", dict(Counter(r.condition for r in all_records)))
for condition in ("AGENT", "AGENT_ITERATIVE"):
    print(condition, dict(Counter(tuple(r.selected) for r in all_records
                                  if r.condition == condition and r.status == "success")))
print("Selection frequency is descriptive; evaluate A/P and quality separately.")
"""
    export = """
import shutil
from datetime import UTC, datetime

from google.colab import files

stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
archive = shutil.make_archive(
    str(RESULTS_ROOT / f"{RUN_LABEL}-{stamp}_results"), "zip",
    root_dir=RESULTS_ROOT, base_dir=RUN_LABEL,
)
files.download(archive)
"""
    cells = [
        cell(
            "# Three-target qualitative-selector development experiment\n\n"
            "Runs Eminescu, Nampeyo and Thoreau sequentially: 108 attempts per selected model. "
            "This is separate from frozen held-out experiments. All v2 questions and answer "
            "requirements are restored. Only selector alignment and iterative complementarity "
            "instructions are updated; all selectors share the current four-modality descriptions; "
            "no modality is forced. Select `previous` with a new run label for the old selector "
            "on the same v2 questions. Gemma uses Transformers 5.19.0.\n\n"
            "Use a fresh GPU runtime; choose a model before installing dependencies. "
            "If installation "
            "requests a restart, restart once and rerun in order. Use a mounted Drive results path "
            "for persistence. Matching attempts, including failures, are preserved on resume. "
            "Do not run concurrent notebooks with the same label. No automatic inference retries. "
            "Run the export cell after an interruption to save partial results.",
            "markdown",
        )
    ]
    cells += [copy.deepcopy(original["cells"][i]) for i in (1, 2, 3, 4, 5, 6, 7, 8)]
    cells += [cell(install), cell(loading), cell(processor_setup)]
    cells += [
        cell("## Development settings and versioned questions", "markdown"),
        cell(controls),
        cell(constants),
        cell("## Shared generation interface", "markdown"),
        cell(source(15)),
        cell("## Embedded target interfaces\nDefinitions only; no model calls.", "markdown"),
        cell(block_cell),
        cell(
            "## Run all three targets\nStarts GPU inference, including an all-modality "
            "preflight per target. Failed preflight stops the batch.",
            "markdown",
        ),
        cell(runner),
        cell("## Summary and export", "markdown"),
        cell(summary),
        cell(export),
    ]
    result = copy.deepcopy(original)
    result["cells"] = cells
    result["metadata"].pop("widgets", None)
    for item in cells:
        if item["cell_type"] == "code":
            item.update(outputs=[], execution_count=None)
    return result


if __name__ == "__main__":
    body = json.dumps(build_notebook(), ensure_ascii=False, indent=1) + "\n"
    print("*** Begin Patch\n*** Add File: " + DESTINATION)
    print("\n".join("+" + line for line in body.splitlines()))
    print("*** End Patch")
