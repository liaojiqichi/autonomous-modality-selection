"""Generate the dual-model formal revision notebook, preserving base inference cells."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from revision_direct_cells import CONTEXT, DECLARATION, INSTALL

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "notebooks/autonomous_modality_selection_heldout.ipynb"

SETTINGS = """
# Separate additive protocol: never write revision results into a historical run.
REVISION_RUN_LABEL = "heldout-answer-revision-v1-001"
REVISION_RESULTS_ROOT = RESULTS_ROOT / REVISION_RUN_LABEL
REVISION_CUMULATIVE_BUDGET = 7
REVISION_REVIEW_TOKENS = 512
"""

EXTENSION_SETUP = """import gc
import inspect

from autonomous_modality.answer_revision import RevisionPolicy
from autonomous_modality.revision_colab import run_target_revisions

REVISION_POLICY = RevisionPolicy(
    maximum_cumulative_cost=REVISION_CUMULATIVE_BUDGET,
    reviewer_tokens=REVISION_REVIEW_TOKENS,
)
REVISION_RUNTIME = {
    "environment": {
        n: importlib.metadata.version(n)
        for n in ("torch", "transformers", "bitsandbytes", "accelerate", "numpy", "Pillow",
                  "rasterio", "matplotlib", "pydantic")
    },
    "image_processor": json.loads(processor.image_processor.to_json_string()),
    "chat_template": getattr(processor, "chat_template", None),
    "tokenizer_chat_template": getattr(processor.tokenizer, "chat_template", None),
    "model_revision": DEPLOYMENT.model_revision,
    "processor_revision": DEPLOYMENT.processor_revision,
    "gpu": torch.cuda.get_device_name(0),
    "cuda": torch.version.cuda,
    "generation_source": inspect.getsource(generate_reply),
}
REVISION_FINGERPRINT = {
    "policy": REVISION_POLICY.model_dump(mode="json"),
    "notebook_sha256": sha256_file(REVISION_NOTEBOOK),
    "runtime": REVISION_RUNTIME,
    "module_sha256": {
        n: sha256_file(PROJECT / "src/autonomous_modality" / n)
        for n in ("answer_revision.py", "revision_colab.py")
    },
    "base_notebook_sha256": sha256_file(FORMAL_NOTEBOOK),
    "protocol_sha256": sha256_file(OVERLAY / "protocol.json"),
}

"""

RUN = """from IPython import get_ipython

batch_shell = get_ipython()
if batch_shell is None:
    raise RuntimeError("Run in Colab/IPython.")
if REVISION_RESULTS_ROOT.resolve() == (RESULTS_ROOT / RUN_LABEL).resolve():
    raise ValueError("Revision and baseline output roots must be separate.")
preserve_json(REVISION_RESULTS_ROOT / MODEL_TAG / f"execution-lock-b{BUDGET}.json", {
    "fingerprint": REVISION_FINGERPRINT,
    "runtime_declaration": RUNTIME_DECLARATION.model_dump(mode="json"),
    "target_batches": [FORMAL.batch_ids(b) for b in range(1, 6)],
    "budget": BUDGET,
})
preserve_json(
    RESULTS_ROOT / RUN_LABEL / MODEL_TAG / f"deployment-lock-b{BUDGET}.json",
    RUNTIME_DECLARATION.model_dump(mode="json"),
)
for TARGET_ID in BATCH_TARGET_IDS:
    print("Starting revision target:", TARGET_ID)
    for cell_source in (TARGET_SETUP_SOURCE, SELECTOR_SOURCE, ANSWER_SOURCE, ITERATIVE_SOURCE):
        batch_shell.run_cell(cell_source, store_history=True).raise_error()
    # Run all original conditions; their saved AGENT record is the shared initial draft.
    batch_shell.run_cell(EXPERIMENT_SOURCE, store_history=True).raise_error()
    source = RESULTS_ROOT / RUN_LABEL
    destination = (REVISION_RESULTS_ROOT / MODEL_TAG / f"crater-{TARGET_ID}"
                   / f"budget-{BUDGET}")
    target_attempts = run_target_revisions(
        globals(), source, destination, REVISION_POLICY,
    )
    print("Revision records:", TARGET_ID, len(target_attempts), "/ 4")
    GENERATION_LOG.clear()
    gc.collect()
    torch.cuda.empty_cache()
print("Revision batch finished:", BATCH_NUMBER)
"""

SUMMARY = """from collections import Counter

counts = Counter()
actions = Counter()
for target_id in BATCH_TARGET_IDS:
    folder = REVISION_RESULTS_ROOT / MODEL_TAG / f"crater-{target_id}" / f"budget-{BUDGET}"
    for path in folder.glob("Q*__AGENT_ANSWER_REVISION__r01.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        counts[item["status"]] += 1
        action = (item.get("result") or {}).get("action")
        if action:
            actions[action["action"]] += 1
print("Revision records:", sum(counts.values()), "/ 24")
print("Statuses:", dict(counts), "Actions:", dict(actions))
print("Saved separately:", REVISION_RESULTS_ROOT)
"""


def code(source: str) -> dict:
    """Build an output-free notebook code cell."""
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def build() -> dict:
    """Copy base inference cells and add one answer-informed revision condition."""
    notebook = json.loads(BASE.read_text(encoding="utf-8"))
    old = copy.deepcopy(notebook["cells"])
    name = "autonomous_modality_selection_answer_revision_formal.ipynb"
    settings = "".join(old[1]["source"])
    settings = (
        "\n".join(
            line
            for line in settings.splitlines()
            if not any(
                word in line
                for word in ("MODE =", "DEV_RESULTS_ZIP", "PREPARATION", "APPROVAL", "# For Qwen")
            )
        )
        + "\n"
        + SETTINGS
    )
    settings += f'REVISION_NOTEBOOK = PROJECT / "notebooks/{name}"\n'
    settings = settings.replace(
        'MODEL_ID = "google/gemma-4-E4B-it"', 'MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"'
    )
    settings = settings.replace(
        'MODEL_REVISION = "ee0ef6023621cff504d758262d4e04895a5af4a2"',
        'MODEL_REVISION = ""  # Supply the selected immutable checkpoint revision.',
    )
    settings = settings.replace(
        'RUN_LABEL = "heldout-four-modality-prompt-v11-001"',
        'RUN_LABEL = "heldout-revision-baselines-direct-001"',
    )
    settings = settings.replace(
        "heldout-answer-revision-v1-001", "heldout-answer-revision-direct-001"
    )
    loading = "".join(old[7]["source"])
    loading = loading.replace('if MODE == "prepare" and ', "if ")
    loading = loading.replace('if MODE == "formal":', "if DEPLOYMENT.image_processor_config:")
    loading = loading.replace("approved environment", "configured environment")
    loading = loading.replace("differs from approval", "differs from the configured revision")
    loading = loading.replace("the approved 4-bit model", "a 4-bit model")
    target_setup = "".join(old[10]["source"])
    target_setup = target_setup.replace(
        '"runtime_approval_sha256": sha256(APPROVAL_PATH)',
        '"runtime_declaration_sha256": sha256(DEPLOYMENT_PATH)',
    )
    notebook["cells"] = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Formal answer-informed revision experiment (Qwen or Gemma)\n\n",
                "Run cells in order. This notebook starts formal execution directly and records ",
                "the actual runtime configuration. It performs no development inference. ",
                "Select a model, its immutable revision, and a six-target batch. ",
                "Original conditions ",
                "are preserved; each saved AGENT answer is reviewed once for KEEP or RESELECT. ",
                "Completed records are retained when resuming.\n",
            ],
        },
        code(settings),
        old[2],
        code(CONTEXT),
        code(INSTALL),
        code(loading),
        old[8],
        code(EXTENSION_SETUP + DECLARATION),
        code(target_setup),
        *old[11:15],
        code(RUN),
        code(SUMMARY),
    ]
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"], cell["execution_count"] = [], None
    notebook["metadata"].pop("widgets", None)
    return notebook


if __name__ == "__main__":
    target = ROOT / "notebooks/autonomous_modality_selection_answer_revision_formal.ipynb"
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(target)
