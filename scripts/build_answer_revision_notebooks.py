"""Generate the dual-model formal revision notebook, preserving base inference cells."""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "notebooks/autonomous_modality_selection_heldout.ipynb"

SETTINGS = """
# Separate additive protocol: never write revision results into a historical run.
REVISION_RUN_LABEL = "heldout-answer-revision-v1-001"
REVISION_RESULTS_ROOT = RESULTS_ROOT / REVISION_RUN_LABEL
REVISION_CUMULATIVE_BUDGET = 7
REVISION_REVIEW_TOKENS = 512
REVISION_APPROVAL_PATH = APPROVAL_DIR / f"{MODEL_TAG}-answer-revision-v1-approval.json"
REVISION_PREPARATION_DIR = PREPARATION_DIR / "answer-revision-v1"
"""

EXTENSION_SETUP = """import gc
import inspect

from autonomous_modality.answer_revision import InitialAnswer, RevisionPolicy, RevisionResult
from autonomous_modality.revision_colab import execute_revision, run_target_revisions

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
if MODE == "formal":
    REVISION_APPROVAL = json.loads(REVISION_APPROVAL_PATH.read_text(encoding="utf-8"))
    if REVISION_APPROVAL["fingerprint"] != REVISION_FINGERPRINT:
        raise ValueError("Revision deployment changed; prepare and review a new development run.")
    validation_file = Path(REVISION_APPROVAL["validation_file"])
    if sha256_file(validation_file) != REVISION_APPROVAL["validation_sha256"]:
        raise ValueError("Revision development validation changed.")
    validation = json.loads(validation_file.read_text(encoding="utf-8"))
    if (validation["fingerprint"] != REVISION_FINGERPRINT
            or validation["split"] != "development"
            or validation["case_id"] not in (16604, 5031, 2179)
            or set(validation["attempts"]) != {"Q1", "Q2", "Q3", "Q4"}):
        raise ValueError("Invalid revision validation.")
    for payload in validation["attempts"].values():
        if RevisionResult.model_validate_json(json.dumps(payload)).status != "success":
            raise ValueError("Revision development validation includes a failure.")
"""

DEVELOPMENT = """# Validate the new mechanism on development evidence before formal execution.
if MODE == "prepare":
    REVISION_PREPARATION_DIR.mkdir(parents=True, exist_ok=True)
    preserve_json(REVISION_PREPARATION_DIR / "config.json", REVISION_FINGERPRINT)
    revision_checks = {}
    for spec in QUESTIONS:
        qid = spec["question_id"]
        source = PREPARATION_DIR / f"{qid}__AGENT.json"
        draft = json.loads(source.read_text(encoding="utf-8"))
        if draft["status"] != "success":
            raise ValueError("Development AGENT draft must be successful.")
        initial = InitialAnswer(
            model=MODEL_NAME, case_id=CASE_ID, question_id=qid,
            question=spec["text"].replace("{crater}", CASE_NAME),
            selected=draft["selected"], answer=draft["answer"],
            source_record_sha256=sha256_file(source), source_path=str(source),
            source_metadata_sha256=sha256_file(PREPARATION_DIR / "validation.json"),
        )
        target = REVISION_PREPARATION_DIR / f"{qid}.json"
        if target.exists():
            result = RevisionResult.model_validate_json(target.read_bytes())
            if result.initial != initial or result.policy != REVISION_POLICY:
                raise ValueError("Existing revision preparation differs.")
        else:
            with target.with_suffix(".started.json").open("x", encoding="utf-8") as stream:
                json.dump({"source_sha256": initial.source_record_sha256}, stream)
            GENERATION_LOG.clear()
            result = execute_revision(globals(), spec, initial, REVISION_POLICY)
            preserve_json(target, result.model_dump(mode="json"))
            preserve_json(target.with_suffix(".generations.json"), {"calls": GENERATION_LOG})
            GENERATION_LOG.clear()
            gc.collect()
            torch.cuda.empty_cache()
        revision_checks[qid] = result.model_dump(mode="json")
        print(qid, result.status, result.action)
        if result.status != "success":
            raise ValueError("Review the failed attempt; use a fresh preparation label.")
    preserve_json(REVISION_PREPARATION_DIR / "validation.json", {
        "split": "development", "case_id": int(CASE_ID),
        "fingerprint": REVISION_FINGERPRINT, "attempts": revision_checks,
    })
"""

APPROVE = """
if MODE == "prepare" and CONFIRM_DEVELOPMENT_REVIEW:
    revision_validation = REVISION_PREPARATION_DIR / "validation.json"
    reviewed = json.loads(revision_validation.read_text(encoding="utf-8"))
    if reviewed["fingerprint"] != REVISION_FINGERPRINT:
        raise ValueError("Revision settings changed after preparation.")
    if set(reviewed["attempts"]) != {"Q1", "Q2", "Q3", "Q4"}:
        raise ValueError("Four revision development checks are required.")
    for payload in reviewed["attempts"].values():
        if RevisionResult.model_validate_json(json.dumps(payload)).status != "success":
            raise ValueError("A revision development check failed.")
    preserve_json(REVISION_APPROVAL_PATH, {
        "approved_by": REVIEWER, "fingerprint": REVISION_FINGERPRINT,
        "validation_file": str(revision_validation),
        "validation_sha256": sha256_file(revision_validation),
    })
    print("Revision approval saved:", REVISION_APPROVAL_PATH)
"""

RUN = """if MODE != "formal":
    raise RuntimeError("Review development checks, approve, then select MODE='formal'.")
from IPython import get_ipython

batch_shell = get_ipython()
if batch_shell is None:
    raise RuntimeError("Run in Colab/IPython.")
if REVISION_RESULTS_ROOT.resolve() == (RESULTS_ROOT / RUN_LABEL).resolve():
    raise ValueError("Revision and baseline output roots must be separate.")
preserve_json(REVISION_RESULTS_ROOT / MODEL_TAG / f"execution-lock-b{BUDGET}.json", {
    "fingerprint": REVISION_FINGERPRINT,
    "base_approval": APPROVAL.model_dump(mode="json"),
    "target_batches": [FORMAL.batch_ids(b) for b in range(1, 6)],
    "budget": BUDGET,
})
preserve_json(
    RESULTS_ROOT / RUN_LABEL / MODEL_TAG / f"deployment-lock-b{BUDGET}.json",
    APPROVAL.model_dump(mode="json"),
)
for TARGET_ID in BATCH_TARGET_IDS:
    print("Starting revision target:", TARGET_ID)
    for cell_source in (TARGET_SETUP_SOURCE, SELECTOR_SOURCE, ANSWER_SOURCE, ITERATIVE_SOURCE):
        batch_shell.run_cell(cell_source, store_history=True).raise_error()
    # Run all original conditions; their saved AGENT record is the shared initial draft.
    batch_shell.run_cell(EXPERIMENT_SOURCE, store_history=True).raise_error()
    source = RESULTS_ROOT / RUN_LABEL
    destination = (REVISION_RESULTS_ROOT / MODEL_TAG / f"crater-{CASE_ID}"
                   / f"budget-{BUDGET}")
    target_attempts = run_target_revisions(
        globals(), source, destination, REVISION_POLICY,
    )
    print("Revision records:", CASE_ID, len(target_attempts), "/ 4")
    GENERATION_LOG.clear()
    gc.collect()
    torch.cuda.empty_cache()
print("Revision batch finished:", BATCH_NUMBER)
"""

SUMMARY = """if MODE != "formal":
    raise RuntimeError("This summary is for formal batches only.")
from collections import Counter

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
    settings = "".join(old[1]["source"]) + SETTINGS
    settings += f'REVISION_NOTEBOOK = PROJECT / "notebooks/{name}"\n'
    settings = settings.replace(
        'MODEL_ID = "google/gemma-4-E4B-it"', 'MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"'
    )
    settings = settings.replace(
        'MODEL_REVISION = "ee0ef6023621cff504d758262d4e04895a5af4a2"',
        'MODEL_REVISION = ""  # Supply the selected model immutable commit.',
    )
    settings = settings.replace(
        'PREPARATION_LABEL = "gemma-pinned-validation-001"',
        'PREPARATION_LABEL = "answer-revision-validation-001"',
    )
    settings = settings.replace(
        'RUN_LABEL = "heldout-four-modality-prompt-v11-001"',
        'RUN_LABEL = "heldout-revision-baselines-001"',
    )
    settings = settings.replace(
        'APPROVAL_PATH = APPROVAL_DIR / f"{MODEL_TAG}-approval.json"',
        'APPROVAL_PATH = APPROVAL_DIR / f"{MODEL_TAG}-revision-base-approval.json"',
    )
    settings = settings.replace(
        '# @param ["Qwen/Qwen3-VL-8B-Instruct", "google/gemma-4-E4B-it"]',
        "# Choose Qwen/Qwen3-VL-8B-Instruct or google/gemma-4-E4B-it.",
    )
    old[1] = code(settings)
    old[17] = code("".join(old[17]["source"]) + APPROVE)
    old[19] = code(RUN)
    old[20] = code(SUMMARY)
    old[0]["source"] = [
        "# Formal answer-informed revision experiment (Qwen or Gemma)\n\n",
        "Choose either supported model and its immutable revision. The original AGENT and ",
        "AGENT_ITERATIVE remain unchanged. The added AGENT_ANSWER_REVISION condition reviews ",
        "the same run's AGENT draft, then keeps it or selects a complete replacement set.\n\n",
        "Each final set has at most two modalities under budget 4 (sensitivity 3). Cumulative ",
        "unique access is capped at 7 ordinal units. Initial and additional inference are ",
        "recorded separately. Revision output is written in a separate directory.\n\n",
        "Run prepare on development evidence, inspect the original 12 checks and four revision ",
        "checks, and approve the deployment. Formal mode runs six targets per batch, five ",
        "batches in total: 216 original records and 24 revision records per batch. ",
        "KEEP reuses the original answer verbatim. See docs/answer_informed_revision.md.\n",
    ]
    old[18]["source"] = ["## Run six targets and save revision records separately\n"]
    # Setup follows the existing generation function, before preparation approval.
    notebook["cells"] = [*old[:9], code(EXTENSION_SETUP), *old[9:17], code(DEVELOPMENT), *old[17:]]
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"], cell["execution_count"] = [], None
    notebook["metadata"].pop("widgets", None)
    return notebook


if __name__ == "__main__":
    target = ROOT / "notebooks/autonomous_modality_selection_answer_revision_formal.ipynb"
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(target)
