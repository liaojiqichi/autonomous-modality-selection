# Answer-informed revision

## Formal condition

`AGENT_ANSWER_REVISION` is an additional condition for both Qwen3-VL-8B-Instruct
and Gemma-4-E4B-it. Existing AGENT, AGENT_ITERATIVE, NO_DATA, ALL_AVAILABLE
and five shared RANDOM draws retain their definitions. Original protocol files,
questions, data packages and previous runs are preserved.

1. Run one-shot AGENT and save its selection and answer.
2. Give the same model the question, requirements, asset descriptions, original
   evidence, initial answer and feasible replacement combinations.
3. Make exactly one review call: KEEP or RESELECT.
4. KEEP returns the initial answer verbatim. RESELECT chooses a complete input
   combination and generates one fresh answer using the shared answer policy.
5. The final answer receives only the selected data and original question
   requirements. It does not receive the draft or selector rationales.

The reviewer distinguishes missing evidence from unused existing evidence. It
compares expected analytical approaches (A) and explanatory perspectives (P)
separately. Scientific validity and evidence fidelity remain independent checks.
There is no fixed idea quota, A+P objective or mandatory optical selection.
Improving richness remains a hypothesis to test.

## Budgets and stopping

Each answer uses one or two modalities within budget 4 (sensitivity budget 3).
Ordinal costs are catalogue 1 and optical, topography and multispectral 2 each.
The cumulative union of accessed modalities has a separate budget of **7**.
Dropping data from the final input does not refund previous access. Reusing a
package adds no new access cost; processing it again still uses compute.
Catalogue + topography -> optical + topography has final input cost 4, additional
access cost 2 and cumulative access cost 5.

There is one review and at most one additional answer call. KEEP does not
regenerate the answer. The current set is omitted from replacement options;
empty sets are excluded, matching the one-shot selector. Invalid actions and
truncations remain failed/incomplete attempts, with no hidden retries or
score-based selection between initial and revised answers.

## Dual-model formal notebook

Use `notebooks/autonomous_modality_selection_answer_revision_formal.ipynb` for
either model. It reuses the working formal loading/generation cells, frozen
questions and inputs, and original five-condition runner. Each target then uses
its saved AGENT answers as revision starting points. The shared draft is generated
once, making initial/final comparisons paired.

Per six-target batch there are 216 original-condition records and 24 revisions:
240 total. Across 30 targets this is 1,200 records per model, including 120
revisions. Record counts differ from generation-call counts because KEEP reuses
an answer.

### Run order

1. Sync the repository once before starting; keep its commit fixed across batches.
2. Choose `MODEL_ID` and set its actual immutable `MODEL_REVISION` and
   `PROCESSOR_REVISION`. Do not use a Gemma revision with Qwen. The retained
   adapters use Transformers 4.57.6 for Qwen and 5.19.0 for Gemma.
3. Set the existing formal dataset folder/ZIP on Drive and use unused run labels.
4. Run the cells in order. The notebook installs the configured dependencies,
   loads the selected model, records its actual runtime and starts execution.
   If already imported libraries change, restart the session once and rerun.
5. Choose `BATCH_NUMBER` 1--5. A matching loaded model can be reused.
   Each batch contains six frozen targets. Existing matching records are retained.

The notebook contains no preparation inference, development-results ZIP dependency
or approval step. Its runtime declaration records versions and settings without
claiming that a development validation run passed. Previous Gemma checks do not
establish Qwen GPU compatibility. Environment, immutable checkpoint, dataset and
resume checks remain active.

Original records go below `RESULTS_ROOT / RUN_LABEL`; revision records go below
`REVISION_RESULTS_ROOT`. Keep both directories. The initial record is checked
against its metadata hash, scenario, evidence hashes, effective processor,
immutable deployment revisions, environment, prompts, generation settings and
logged answer input. Only a successful EOS-terminated initial answer is eligible.
Failed initial attempts produce blocked revision records.

An exclusive `.started.json` journal is written before each revision attempt.
An interrupted attempt without a result stops resume for explicit recovery.
Preserve journals/logs and document any new run. Existing errors and blocked
records are retained; there is no automatic retry.

## Reporting

Report paired initial/final A and P separately, independent quality checks,
KEEP/reselection frequency, changed combinations, failures and paired sample size.
Report final input, cumulative access and additional access costs separately.
`generation_log` contains new calls; `initial_generation_log` records the shared
baseline dependency. Present incremental and full-pipeline costs; avoid double
counting shared baseline calls in physical execution totals.

The cumulative budget and additional inference exceed those of one-shot selection
and the original iterative condition. A higher score alone does not establish
greater efficiency. A separate same-input regeneration control could help isolate
the contribution of reselection; it is not included in this version.

## Implementation and verification

`answer_revision.py` defines the actions, feasible sets and accounting.
`revision_colab.py` validates saved drafts and records attempts.
`scripts/build_answer_revision_notebooks.py` generates the formal notebook from
the unchanged base notebook; run Ruff formatting after regeneration.

Tests use invented metadata and scripted outputs, covering KEEP identity,
replacement, cumulative budgets, invalid actions, truncations, provenance drift,
interrupted runs and preservation of inference cells. Passing these tests does
not establish GPU compatibility or scientific gains. Actual inference runs in Colab.
