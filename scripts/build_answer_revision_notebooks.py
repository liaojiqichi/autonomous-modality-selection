"""Generate the dual-model formal revision notebook, preserving base inference cells."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from revision_direct_cells import CONTEXT, DECLARATION, INSTALL

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "notebooks/autonomous_modality_selection_heldout.ipynb"

SETTINGS = """
# Separate additive protocol: never write revision results into a historical run.
REVISION_RESULTS_ROOT = RESULTS_ROOT / RUN_LABEL
REVISION_AUDIT_TOKENS = 2048
REVISION_REVIEW_TOKENS = 512
# All selectors use the same current modality declarations.
"""

EXTENSION_SETUP = """import gc
import inspect

from autonomous_modality.evidence_revision import PROMPT_VERSION, RevisionPolicy
from autonomous_modality.modality_descriptions import ASSET_DESCRIPTION_VERSION
from autonomous_modality.revision_colab import run_target_revisions

REVISION_POLICY = RevisionPolicy(
    audit_tokens=REVISION_AUDIT_TOKENS,
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
    "reviewer_prompt_version": PROMPT_VERSION,
    "asset_description_version": ASSET_DESCRIPTION_VERSION,
    "asset_description_scope": "all_selectors",
    "policy": REVISION_POLICY.model_dump(mode="json"),
    "notebook_sha256": sha256_file(REVISION_NOTEBOOK),
    "runtime": REVISION_RUNTIME,
    "module_sha256": {
        n: sha256_file(PROJECT / "src/autonomous_modality" / n)
        for n in ("answer_revision.py", "evidence_revision.py",
                  "revision_colab.py", "modality_descriptions.py")
    },
    "base_notebook_sha256": sha256_file(FORMAL_NOTEBOOK),
    "protocol_sha256": sha256_file(OVERLAY / "protocol.json"),
}

"""

RUN = """from IPython import get_ipython

batch_shell = get_ipython()
if batch_shell is None:
    raise RuntimeError("Run in Colab/IPython.")
preserve_json(REVISION_RESULTS_ROOT / MODEL_TAG / f"revision-execution-lock-b{BUDGET}.json", {
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
    for cell_source in (TARGET_SETUP_SOURCE, SELECTOR_SOURCE, ANSWER_SOURCE, EVIDENCE_SOURCE):
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

from autonomous_modality.evidence_revision import summarize_costs
from autonomous_modality.revision_colab import RevisionAttempt

attempts = []
for target_id in BATCH_TARGET_IDS:
    folder = RESULTS_ROOT / RUN_LABEL / MODEL_TAG / f"crater-{target_id}" / f"budget-{BUDGET}"
    for path in folder.glob("Q*__AGENT_ANSWER_REVISION__r01.json"):
        attempts.append(RevisionAttempt.model_validate_json(path.read_bytes()))
summary = summarize_costs([a.result for a in attempts if a.result is not None])
summary["attempt_statuses"] = dict(Counter(a.status for a in attempts))
summary["expected_revision_records"] = len(BATCH_TARGET_IDS) * 4
summary["revision_records"] = len(attempts)
print(json.dumps(summary, indent=2))
summary_path = (RESULTS_ROOT / RUN_LABEL / MODEL_TAG
                / f"cost-summary-b{BUDGET}-batch{BATCH_NUMBER}.json")
summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("All conditions are saved together:", RESULTS_ROOT / RUN_LABEL)
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


def current_execution_sources(old: list[dict]) -> tuple[str, str]:
    """Reuse verified evidence routing and remove the retired iterative experiment branch."""
    evidence = ast.literal_eval(ast.parse("".join(old[13]["source"])).body[0].value)
    tree = ast.parse(evidence)
    functions = [
        ast.get_source_segment(evidence, node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"build_evidence_content", "load_notebook_evidence"}
    ]
    evidence = (
        "from autonomous_modality.iterative import ContentBlock, EvidenceObservation\n"
        "from autonomous_modality.models import InputDataModality\n"
        "PINNED_RECEIPT_SHA256 = sha256(receipt_path)\n\n" + "\n\n".join(functions)
    )
    experiment = ast.literal_eval(ast.parse("".join(old[14]["source"])).body[0].value)
    start = experiment.index('        if self.condition == "AGENT_ITERATIVE":')
    end = experiment.index("        return self", start)
    experiment = experiment[:start] + experiment[end:]
    start = experiment.index('                if condition == "AGENT_ITERATIVE":')
    end = experiment.index("                selection_seconds", start)
    experiment = (
        experiment[:start]
        + (
            "                selected, rationale = select_inputs(\n"
            "                    condition, question, question_id, draw_index=draw_index\n"
            "                )\n"
        )
        + experiment[end:]
    )
    experiment = experiment.replace(', "AGENT_ITERATIVE"', "")
    experiment = experiment.replace(
        "    iterative_selection: IterativeSelection | None = None",
        "    iterative_selection: None = None",
    )
    experiment = experiment.replace("    select_inputs_iterative,\n", "")
    experiment = experiment.replace(
        '    "iterative_policy": ITERATIVE_POLICY.model_dump(mode="json"),\n', ""
    )
    experiment = experiment.replace(
        '    "condition_roles": {"AGENT": "one_shot_ablation": "primary_agent"},',
        '    "condition_roles": {"AGENT": "initial_selection"},',
    )
    # Replace the whole roles line, independent of formatting in the frozen source.
    experiment = "\n".join(
        '    "condition_roles": {"AGENT": "initial_selection"},'
        if '"condition_roles":' in line
        else line
        for line in experiment.splitlines()
    )
    experiment = experiment.replace(", IterativeSelection)", ")")
    experiment = experiment.replace(
        "set(protocol.primary_conditions + protocol.auxiliary_conditions)",
        "(\n    set(protocol.primary_conditions + protocol.auxiliary_conditions)\n"
        '    - {"AGENT_ITERATIVE"}\n)',
    )
    return (
        "EVIDENCE_SOURCE = r'''" + evidence + "'''\n",
        "EXPERIMENT_SOURCE = r'''" + experiment + "'''\n",
    )


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
        'RUN_LABEL = "heldout-four-modality-unified-descriptions-v2-001"',
        'RUN_LABEL = "heldout-evidence-revision-v2-001"',
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
    target_setup = target_setup.replace(
        "4 questions x (1 + 1 + 5 + 1 + 1) = 36 formal attempts.",
        "4 questions x (1 + 1 + 5 + 1) = 32 baseline attempts, plus 4 audited revisions.",
    )
    target_setup = target_setup.replace(
        '"protocol": RECORD_VERSION,',
        '"protocol": RECORD_VERSION,\n'
        '    "experiment_amendment": "evidence-attributed-revision-2.0",',
    )
    evidence_source, experiment_source = current_execution_sources(old)
    notebook["cells"] = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Formal answer-informed revision experiment (Qwen or Gemma)\n\n",
                "Run cells in order. This notebook starts formal execution directly and records ",
                "the actual runtime configuration. It performs no development inference. ",
                "Select a model, its immutable revision, and a six-target batch. ",
                "NO_DATA, ALL_AVAILABLE, RANDOM and AGENT are retained. ",
                "Each AGENT answer is audited, then revised with retained or reselected evidence. ",
                "The earlier iterative condition is retired from this experiment. ",
                "Costs above the threshold remain in the results. ",
                "All conditions share one run folder. ",
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
        *old[11:13],
        code(evidence_source),
        code(experiment_source),
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
