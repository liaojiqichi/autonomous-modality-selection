# Formal Colab runner: 30 targets in five batches

Use `notebooks/autonomous_modality_selection_heldout.ipynb`. The development notebook
remains separate. Each batch has six targets in the original cohort order. Each
target has 36 attempts per model, including the one-shot auxiliary ablation:
216 per batch per model, 2,160 across five batches and two models at budget 4.
Budget 3 is a separate sensitivity run. Five days is a scheduling goal, not a runtime guarantee.

## Required files before inference

1. Make the updated repository, including the new notebook and `heldout_colab.py`,
   available in `/content/autonomous-modality-selection`. Do not update it mid-experiment.
2. Upload/unpack the full `mercury-heldout-four-modality-v2-20261008` release to Drive.
   Point DATASET_ROOT to its directory containing `release.json`, `frozen`,
   `model_inputs` and all 30 `crater-*` folders. The seven-target development download
   does not contain this release. No new formal download URL is assumed.
3. Prepare a separately reviewed runtime-approval JSON for both models and the
   development validation artifacts referenced by it. No approval is fabricated by
   this runner. Missing approval blocks model loading and held-out inference.
4. Set a persistent RESULTS_ROOT, one RUN_LABEL, MODEL_ID, BATCH_NUMBER and BUDGET.
   Run the cells in order. Switching models requires a fresh runtime.

## Frozen protocol and representations

The base data release is checked read-only, including its compact inputs. The
16 October question overlay supplies revised questions and the 120 expanded scenarios.
The runner reads saved random draws; it never resamples them. It reads compact PNGs,
terrain text and multispectral text from `model_inputs/crater-ID` without regeneration.

Only questions were revised in protocol 1.1. Consequently, the runner loads the
base release's frozen answer policy (`english-ap-input-supported-1.0`), inventory
and selector alignment. It does not silently import the newer mutable development
policy. Any adoption of newer prompts or input descriptions requires another explicit
protocol revision and development validation before formal inference.

The Qwen/Gemma loader and generation function reuse the working development adapter.
Checkpoint and processor revisions are explicit immutable commit hashes. The original
protocol's `runtime_approved=false` remains historical; separate reviewed runtime
approval supplies the deployment authorization, without editing the old release.

## Runtime approval schema

`RuntimeApproval` and `Deployment` in `heldout_colab.py` are strict schemas. The top
level has these fields:

- `version`: `heldout-runtime-approval-1`.
- `approved_by`: the person reviewing development validation.
- `protocol_sha256`: SHA-256 of the overlay's `protocol.json`.
- `notebook_sha256`: SHA-256 of the maintained formal notebook file in the checkout.
- `models`: entries for both `Qwen/Qwen3-VL-8B-Instruct` and `google/gemma-4-E4B-it`.

Each model entry contains:

- `model_revision`, `processor_revision`: exact 40-character commit hashes.
- `environment`: exact installed distribution versions, including at least torch,
  transformers, bitsandbytes, accelerate and Pillow. Include all relevant dependencies
  from the validated setup. The runner checks every listed version.
- `image_processor_size`: the actual approved processor size dictionary. Display
  PNG edge 448 is distinct from the model's image preprocessing settings.
- `validation_file`: relative path to the existing development validation artifact,
  resolved from the approval JSON directory; escaping or absolute paths are rejected.
- `validation_sha256`: the actual SHA-256 of that artifact.
- `validation_split`: `development`.
- `reviewed_pass`: true only after reviewing the development validation.
- `validation_notes`: what was checked, including all-modality inputs, the full
  answer cap, selector calls, GPU memory and deterministic decoding.

Hashes can be calculated with `hashlib.sha256(path.read_bytes()).hexdigest()`.
Version information comes from `importlib.metadata.version(distribution)` in the
validated runtime. The approval links evidence of validation; it does not turn an
unreviewed old experiment into a completed validation. Do not merely fill placeholders
to bypass the check. No held-out answer is generated as a tuning preflight.

## Daily batching and recovery

Use BATCH_NUMBER 1 through 5. Both models use the same six targets per batch, but only
one model is resident at a time. Keep RUN_LABEL and the configuration unchanged across
days. The shared execution lock pins both deployments, source hashes, protocol,
dataset identity, budget and batch allocation. Per-target metadata additionally pins
actual processors, environment, functions, input bytes and generation settings.

Each attempt is saved immediately through a temporary file followed by rename. Existing
valid records, including failures and truncations, are retained. A changed configuration
or identity blocks resume. A leftover `.json.tmp` file from interruption also blocks
that attempt; preserve it and investigate before deciding on a documented recovery.
Do not run simultaneous notebooks writing the same experiment. Drive is persistent
storage, not a transactional database; retain periodic copies of the results directory.

Byte-identical compact input snapshots and catalogue records are copied into the
results directory for later annotation. Original science data remain read-only.
The final cell summarizes technical statuses only. Keep A/P evaluation and decisions
about protocol changes separate from held-out generation.

## Verification scope

Offline tests use synthetic metadata and fake generation, including a six-target
216-attempt loop, resume, failure preservation, invalid batch/draw rejection and
runtime-approval checks. These tests do not validate GPU capacity or model quality.
Local full-release verification is read-only and performs no model inference.
