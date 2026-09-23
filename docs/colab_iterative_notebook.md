# Five-condition Colab notebook

Open `notebooks/autonomous_modality_selection_iterative.ipynb` in Colab. This is
a clean derivative of the user's working AP notebook, with all old outputs removed.
The original downloaded notebook is untouched. No scientific data or model weights
are stored in Git. The new notebook does not run acquisition or repeat the pilot.

## Running

1. Authenticate to the private Git repository as before. Section 1 fetches and
   fast-forwards the checkout and refuses to overwrite local changes. If old project
   modules were already imported, restart the runtime before using updated code.
2. With a freshly selected GPU, run the environment/model cells. If the correct
   Qwen model is already loaded, skip pip installation; the load cell reuses it.
   This notebook retains the working Qwen3-VL-8B 4-bit setup. It does not validate
   a new Gemma loading configuration.
3. In section 3, check CASE_DIR and RESULTS_ROOT. The defaults match the uploaded
   notebook: `/content/mercury-pilot-001/crater-16604`, with run `emin-agentic-001`.
   Use a new RUN_LABEL when changing configuration. Persist results to your own
   Drive location if desired; no Drive mount is performed automatically.
4. Run sections 3 through 7 in order. Source TIFFs are checked and read only.
   Only five small PNG views, a terrain text summary and receipts are generated
   under the new run directory. Existing scientific downloads are reused.
5. Download the results archive from the last cell. Examine errors/truncations
   before annotation. Resuming keeps all existing attempts, including failed ones.

## Design

For four questions, each model generates 4 NO_DATA + 4 ALL_AVAILABLE + 20 RANDOM
+ 4 AGENT + 4 AGENT_ITERATIVE = **36 answer-attempt records**. AGENT is the original
one-shot auxiliary ablation. AGENT_ITERATIVE is the new feedback condition.

The working `generate_reply`, `select_inputs`, `build_answer_messages` and
`answer_question` interfaces are retained. The iterative selector sees actual
receipt-verified input content after its first acquisition. Its final answer goes
through the exact same `answer_question` function as every other condition. Selector
rationales are logged separately and never appended to the answer prompt.

The output schema is `colab-ap-agentic-development-3`. Iterative records add an
`iterative_selection` trace; all records retain the familiar `answer`, `selected`,
`selection_generations` and `answer_generations` fields. A failed acquisition prevents
answer generation and retains previously accessed data and cost. Hash checks guard
resume identity and changed evidence. No silent repairs or fallback selections occur.

For compatibility this development pilot retains **ordinal costs 1/2/2 and budget
4** (or budget 3 sensitivity), explicitly labelled `legacy_ordinal_units`. They are
not input-token measurements. Per-call token consumption is logged independently.
The one-shot selector keeps 256 output tokens; the iterative selector allows 512
per call to accommodate the larger action schema, at most two calls. Report this
additional compute opportunity in the ablation; it is not compute-matched.

All five conditions use the same answer policy, evidence routing, 448-pixel views
and 1024-token answer cap. Old successful runs should remain historical, not be
silently merged with this fresh five-condition run. A/P annotation and independent
quality checks remain unchanged. More interactions alone are not an outcome benefit.

## Local verification

Tests parse all notebook cells and execute the actual selection/answer routing and
36-attempt loop with scripted generators and explicitly synthetic input files.
They cover evidence hashes, cumulative budget, failed revisions, resume and final
answer isolation. This is not a GPU/model-validation claim: Colab must still run
the included multimodal input preflight and actual generation.

`examples/upgrade_colab_notebook.py` documents the fail-closed migration from the
original AP notebook. It creates a new file and removes outputs, without executing
the input. The committed notebook has additionally been formatted and linted.
