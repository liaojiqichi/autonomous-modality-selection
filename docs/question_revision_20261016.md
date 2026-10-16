# Shared question revision: 16 October 2026

The user approved replacing the old development and formal-test questions with the
four questions already evaluated on Eminescu, Nampeyo and Thoreau. Their text,
question types and answer requirements are unchanged from the archived development
set `mercury-selection-value-dev-2.0-en`. The shared version is
`mercury-selection-value-2.0-en.1`; its definition has no development-only split field.

The maintained source is `configs/mercury_selection_questions_v2.json`:

1. Check historical morphology classifications against visible structure.
2. Distinguish crater asymmetry from surrounding terrain.
3. Distinguish surface-material contrasts from geometry, illumination and averaging.
4. Examine evidence for post-formation interior modification and alternatives.

Both maintained Colab notebooks, the experiment CLI default and the formal freeze
builder now load this source. Historical `mercury_questions_v1.json` and the separate
seven-question `mercury_questions_v2.json` remain available for reproducing older runs.
No historical answers, raw data or original frozen release were edited.

## Existing formal dataset

`configs/heldout_question_revision_20261016/` is the active small overlay for
`mercury-heldout-four-modality-v2-20261008`. It contains questions, the same cohort,
120 expanded scenarios, protocol 1.1 and a revision manifest. The manifest links the
original release and protocol by SHA-256. Evidence stays in the original dataset.
Only questions and answer requirements change; costs, budgets, model settings,
120 sets of random draws for each budget, 64 human review slots and rubric remain
unchanged. The overlay is approximately 235 KB and contains no model results.

A formal runner must read questions/design/protocol from this overlay and evidence
from the original release. Verify the base release and overlay hashes separately;
do not overwrite the original `frozen` directory. Old release snapshots remain
historical and still contain the original question text. Runtime approval remains
pending; this update does not make the development notebook a formal runner.

To regenerate an overlay into a new, nonexistent folder:

```powershell
python -m autonomous_modality.question_revision `
  experiments/benchmarks/mercury-heldout-four-modality-v2-20261008 `
  output/question-revision-new
```

## Colab migration

Pull the updated repository before running setup. Reload the maintained notebook's
question-loading cell. Remove any personal cell that subsequently replaces QUESTIONS
with old hardcoded questions. Confirm the loaded version is
`mercury-selection-value-2.0-en.1`, and use a new RUN_LABEL for each new configuration.
Do not merge old-question and revised-question results into one condition mean.
Question changes are a protocol revision, not evidence that the selector improved.

The three development targets remain development targets. This revision does not
move them into the formal held-out cohort or claim independent human validation.
