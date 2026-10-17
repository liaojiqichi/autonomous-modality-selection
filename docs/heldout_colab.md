# Formal Colab runner: preparation and five six-target batches

Open `notebooks/autonomous_modality_selection_heldout.ipynb` from the updated repository.
It has two modes: `prepare` validates a pinned deployment on existing development
inputs; `formal` runs six held-out targets. No human approval file needs to be
hand-written. Each model is confirmed independently.

## First run: Gemma preparation

1. Put `four-modality-three-target-dev-001_results.zip` in Google Drive. Set
   `DEV_RESULTS_ZIP` to its location. The notebook reuses its actual Eminescu input
   snapshots, verifying their receipt hashes. The archive omitted catalogue.json;
   its catalogue is recovered from consistent recorded ALL_AVAILABLE input messages.
   This provenance is saved explicitly. No scientific data is invented or downloaded.
2. Select `MODE="prepare"`. The default model and processor revision is
   `ee0ef6023621cff504d758262d4e04895a5af4a2` for Gemma. This is the newly selected
   revision, not a recovered historical revision. Qwen requires its own explicit SHA.
3. Run the cells in order. Preparation installs the previously used Gemma library
   versions (Transformers 5.19.0, bitsandbytes 0.50.2, accelerate 1.15.0, Pillow 12.3.0).
   Torch remains the Colab-provided version and is recorded rather than silently
   reinstalled. If imported libraries change, restart the session and run again.
   Hugging Face model access must already be authorized; keep tokens out of code.
4. The development cell runs Q1-Q4 for ALL_AVAILABLE, AGENT and AGENT_ITERATIVE:
   twelve answers plus their selector calls. It uses the same answer and acquisition
   functions as the formal notebook. The answer cap is 1024; selector cap 512;
   input cap 8192; answer repetition penalty 1.2; decoding is greedy.
5. Inspect the saved attempts, answers and acquisition traces. Set
   `CONFIRM_DEVELOPMENT_REVIEW=True` only after review and rerun that cell. It checks
   that all twelve attempts and all logged generations completed with EOS, then
   saves a model-specific approval. This is technical readiness, not scientific
   validation or an assessment of A/P superiority.

The final formal batch cell intentionally stops in preparation mode. Set
`MODE="formal"` and rerun cells in order after confirmation. A matching model can
remain loaded; changing model/revision requires a fresh runtime.

Failures and truncations remain saved. Preparation will not secretly retry them.
Resolve their cause, then choose a new PREPARATION_LABEL. Never mark an unsuccessful
validation as passed. If changing an already approved deployment, preserve its
approval and use a new APPROVAL_DIR and formal RUN_LABEL.

## Formal data and daily batches

Upload the complete `mercury-heldout-four-modality-v2-20261008` release directory
or its ZIP to Drive. Set DATASET_ROOT, or DATASET_ZIP and DATASET_EXTRACT. ZIP
extraction checks paths and does not overwrite an existing extraction. If extraction
was interrupted, inspect the partial directory and choose a new destination.
Full release verification runs before any held-out inference.

Choose BATCH_NUMBER 1 through 5. Each batch uses six targets in frozen cohort order.
There are 36 attempts per target per model, including the one-shot auxiliary
ablation: 216 per batch and 2,160 across five batches and both models at budget 4.
Budget 3 is a separate sensitivity run. Five days is a scheduling plan, not a
runtime guarantee. The notebook reads saved shared random draws without resampling.

Keep RUN_LABEL and configuration fixed across batches. Every attempt is saved
immediately to Drive. Existing successful, failed and truncated attempts are
preserved. Changed configurations block resume; orphan temporary files require
inspection. Do not run simultaneous writers to the same output folder.

The shared execution lock records dataset, questions, prompt amendment, code,
budget and batches. Separate per-model locks record deployments. Thus Gemma can
run before Qwen is ready, while later cross-model runs must use the same shared
design. Qwen must pass its own development validation.

## Explicit protocol amendment

The original release and question-only overlay remain unchanged. The additional
`configs/heldout_runtime_revision_20261016` amendment adopts the development 1.1
answer policy and content inventory, the matching selector alignment, and
independent deployment confirmation. Its exact prompt bytes are hash-pinned.
The amendment hash is saved in validation, formal metadata and shared run locks.
Input data, target allocation, question families, random draws, ordinal costs and
budgets are inherited unchanged. Revalidate if prompts or implementation change.

The processor's complete configuration is recorded. Gemma uses max_soft_tokens
and image_seq_length (280 for this validation); Qwen uses its size/pixel limits.
The displayed PNG edge of 448 is distinct from these model settings. Both models
use four-bit NF4 with double quantization and float16 compute.

## Verification scope

Local tests use synthetic input metadata and fake inference, including the actual
preparation/confirmation cells, single-model approval, failure rejection, formal
216-attempt batching and resume. These tests do not establish GPU capacity or
model quality. Actual model validation runs explicitly in Colab.
