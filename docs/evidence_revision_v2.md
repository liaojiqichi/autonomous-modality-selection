# Evidence-attributed answer revision

Use `notebooks/autonomous_modality_selection_answer_revision_formal.ipynb` for
Qwen or Gemma. Select a fresh run label and run its cells in order. Existing
results remain unchanged. No additional preparation inference is required.

## Conditions and output

Each target produces 32 baseline answers (four questions, with five RANDOM draws
and one each of NO_DATA, ALL_AVAILABLE and AGENT) and four answer revisions.
AGENT_ITERATIVE is removed from this active experiment. Historical code remains
available for reading and reproducing earlier runs.

All answer files share:
`RESULTS_ROOT/RUN_LABEL/MODEL_TAG/crater-ID/budget-N/`.
Condition names distinguish baseline and revision files. Configuration and cost
summaries are stored under this same run. There is no separate revision run label.

## Workflow

1. Audit every nonempty line of the initial AGENT answer. Identify the source
   modality and exact text quote or image location. Label each line supported,
   proposed, unsupported, misused or uncertain. Mixed lines with unsupported
   content are removed as a whole.
2. Retain supported statements and evidence-grounded proposals. Assess their
   remaining value for the question and the information still needed.
3. Keep the initial modalities or choose a replacement set. Consider lost evidence,
   new evidence and cost. At most two final modalities are permitted.
4. Remove retained statements that depend on discarded modalities. Generate a
   complete revised answer from the final evidence and retained statements,
   including when the decision is KEEP.

Text quotations and source identifiers are checked deterministically. Scientific
support and visual interpretation remain model judgments and require independent
quality evaluation. Audit output does not establish factual correctness.

## Cost accounting

Costs remain ordinal: catalogue 1, each other modality 2. The result records
initial cost, final retained-modality cost, their difference, additional accessed
cost and cumulative cost over the union of accessed modalities. Discarded modalities
are excluded from final cost but remain in cumulative access cost.

Revision budgets are thresholds. An over-budget final selection is executed and
retained in paired cost means; it is also counted explicitly. Failed, truncated
and incomplete records are reported separately, with decided and acquired
selection counts so that an unexecuted decision is not treated as successful work.

With at most two modalities, final cost cannot exceed the primary threshold of 4
at current prices. It can exceed threshold 3 in sensitivity runs. Cumulative
access cost can exceed either threshold after replacement.

Audit generation uses 2048 tokens and selection review 512; answer generation
retains the existing settings. Each stage records its output and termination
status. There are no hidden retries. Local tests use fixtures; Colab must verify
GPU memory and scientific behavior with the real model.
