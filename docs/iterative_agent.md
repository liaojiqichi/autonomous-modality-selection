# Bounded evidence-acquisition experiment (development extension)

Version: `bounded-evidence-agent-1.0`. This extension implements the newly agreed
feedback experiment. It does not rewrite the signed proposal, historical protocol,
data packages, notebooks or old results. No model is loaded by importing its code.

## Conditions and compatibility

The new primary comparison uses NO_DATA, ALL_AVAILABLE, RANDOM and AGENT_ITERATIVE.
AGENT keeps its original **one-shot** meaning and is retained as an auxiliary
ablation. Never relabel historical AGENT records as iterative. The existing CLI
still prepares the original four conditions by default. Opt in explicitly:

```powershell
python -m autonomous_modality.experiments --benchmark experiments/benchmarks/mercury-screened-v2-20260907 --output experiments/primary/iterative-development-new --include-iterative --budget 4 --seed 42
```

This is OFFLINE preparation, with both agent conditions pending. The old budget
arguments use legacy ordinal units. The preparation records an experimental
extension identifier; it is not a new claim of conformity to a signed proposal.
Five random draws plus the other four conditions give nine attempts per scenario
and model (36 for four questions on one crater/model). Formal counts and held-out
use should be finalized after development testing. Historical results remain separate.

## Acquisition rules

1. The selector initially receives the question, inventory metadata and constraints.
2. REQUEST_MODALITY names one scientific modality and gives a short reason combining
   the evidence need and intended use (at most 240 characters). Deterministic code
   validates the compact response; FINISH uses only action and reason.
3. The system reads the existing verified package and returns its actual text/images.
4. After the first acquisition, the agent can FINISH or request one other modality.
5. After two acquisitions the system stops and generates the answer. A lower
   modality cap or lack of feasible additions can also trigger system termination.

There are at most two selector calls, two acquisitions and one observation-informed
revision. A valid initial FINISH is allowed if no modality is required. Required
modalities must remain attainable after each acquisition. Forbidden, unavailable,
unknown, duplicate and over-budget requests are rejected. There are no silent
repairs, fallbacks or retries; raw invalid output stays in the error trace.

The current action prompt is `bounded-evidence-selector-ap-1.2-compact`, with trace
schema `iterative-selection-1.1`. The legacy `AgentAction` and trace schema 1.0 remain
readable for archival analysis; new model calls are parsed as `CompactAgentAction`.
Legacy information_gap/intended_use response fields are rejected by the new parser.
Malformed JSON and overlong reasons remain visible failures without repair.

`DataAssetProfile.content_inventory` holds versioned available/absent field names,
model-visible representations and access limits. Values are withheld until acquisition.
The current Colab notebook supplies matching inventories to both selectors using
`development_inventory()` from `development_inputs.py`. Generic requests may omit the
inventory when content is unknown; the selector must not infer missing fields.
For custom manifest-based callers, explicitly supply inventories matching that
package and give the one-shot comparator the same declarations. The provided
development inventory describes the existing 17-sample terrain representation;
review it before applying it to other packages or sampling settings.

Model FINISH and system stop are recorded separately. The latter is not a fabricated
agent action. The final answer uses all successfully acquired inputs in a fixed
modality order, with no selector rationale, condition label or unselected inventory.
It uses a fresh context: only the shared answer prompt and evidence are passed.

## Costs and fairness

`IterativePolicy.cost_unit` is mandatory: `input_tokens` or `legacy_ordinal_units`.
`cost_definition` must explain the chosen accounting method. The request's asset
costs and budget must use that same unit. The runner does not estimate tokens from
file size, image count or the old 1/2/2 numbers.

For token experiments, externally measure and freeze each complete representation
package with the actual model processor, image settings and prompt convention.
Document which label/wrapper tokens the measurements include and use identical
tables for RANDOM, AGENT and AGENT_ITERATIVE within a model/scenario. Token counts
can differ between model families. Validate total context and image limits separately;
an additive evidence budget is not a guarantee that the full prompt fits a model.

All accessed modalities accumulate cost; data cannot be removed or refunded. A
loader failure is conservatively charged as an attempted access and aborts that
attempt. Invalid requests rejected before loading incur no new evidence cost.
Re-presenting an already acquired package incurs inference tokens but does not
consume a second evidence-access allocation. Per-call input/output tokens, timing
and peak GPU memory are separate from cumulative evidence cost.

AGENT_ITERATIVE has additional inference opportunity relative to the one-shot
ablation. Report that overhead alongside A/P effects; the comparison alone does not
isolate feedback from additional computation. Use the same evidence representation,
answer prompt, checkpoint, decoding and output cap across newly run conditions.
If older conditions used preview-only inputs, rerun matched controls with the new
packages before making quantitative claims.

## Colab integration (existing loaded model)

Keep the existing model loading, `generate_reply`, one-shot `select_inputs` and
baseline code. There is no monkey-patching or dependency on `original_select_inputs`.
The notebook bridge expects `generate_reply` to append one actual statistics entry
to `GENERATION_LOG` with `finish_reason`, `input_tokens`, `output_tokens`, and
optionally `peak_gpu_gib`. Recreate the bridge after replacing that list in Colab.

```python
import sys
from pathlib import Path

# PROJECT is the existing repository root in Colab.
sys.path.insert(0, str(PROJECT / "extensions/evidence_views_v1/src"))
sys.path.insert(0, str(PROJECT / "examples"))

from autonomous_modality.iterative import IterativePolicy
from autonomous_modality.iterative_colab import notebook_generator
from colab_iterative import run_scenario

generate = notebook_generator(generate_reply, GENERATION_LOG)
```

Run the new group separately first; its trace has a new schema. The function below
requires explicit inputs, rather than assuming notebook globals or silently using
an old preview path:

```python
def run_new_condition(
    request,  # InputSelectionRequest for this question; explicit cost table/budget
    package_root: Path,  # existing evidence_views_v1 folder containing manifest.json
    case_id: int,  # same crater as the question; checked against the package
    model_id: str,  # actual loaded checkpoint; pin revision/config in the run metadata
    shared_answer_prompt: str,  # exact same full question/requirements prompt as other conditions
    destination: Path,  # NEW run directory, e.g. .../Q1__AGENT_ITERATIVE.json
    answer_max_new_tokens: int,
    cost_unit: str,
    cost_definition: str,
):
    return run_scenario(
        request,
        IterativePolicy(cost_unit=cost_unit, cost_definition=cost_definition),
        generate,
        package_root=package_root,
        case_id=case_id,
        model_id=model_id,
        shared_answer_prompt=shared_answer_prompt,
        answer_max_new_tokens=answer_max_new_tokens,
        destination=destination,
    )
```

Use `input_tokens` only with measured token costs. For a legacy-cost development
smoke test explicitly use `legacy_ordinal_units` and describe the actual table.
No data download or reconstruction is required. `evidence_view_loader` verifies
file checksums, pins the manifest and returns the same model-visible content as the
existing adapter. Local integrity verification reads all files but only acquired
evidence enters the model prompt. Full raster TIFF/CSV files remain local; the model
receives the existing numeric text, profile images and local/context previews.

Save the existing notebook CONFIG, model revision/quantization, processor settings,
adapter version and shared answer prompt alongside the results. Generate into a
fresh directory. The save function refuses to overwrite an existing attempt.
Preserve error and truncated records; reruns must use a new attempt/run identity.

## Result interpretation and verification

`selection.turns` retains raw generations, parsed actions, actual observations and
hashes, per-turn duration and reason codes. `selection.stop_actor` identifies model
versus system termination. `answer_generation` contains the final answer and its
generation statistics; length stops are `truncated`, unknown stops `unverified`.
An unsuccessful selection prevents the answer call.

Continue the A/P rubric and independent scientific-validity/evidence-fidelity checks.
Additional descriptive measures are acquisition count, requested modalities, active
FINISH rate, system-stop rate, failures and inference overhead. Multiple turns are
one answer attempt, not independent experimental observations. Test fixtures are
labelled `execution_kind="test"` and never count as model or planetary results.

Run all checks with the project Python 3.12+ environment:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest
```
