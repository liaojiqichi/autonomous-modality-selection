# Shared modality descriptions

Version: `mercury-four-modality-descriptions-2.0`.

`src/autonomous_modality/modality_descriptions.py` supplies the descriptions and
inventories for one-shot AGENT, AGENT_ITERATIVE and answer-informed revision.
Every active notebook builds ASSETS through `describe_assets` and records
`asset_description_scope: all_selectors`. The reviewer checks that its inputs
match the initial experiment configuration before calling a model.

Open the updated notebook from GitHub and run its setup in order using a fresh
run label. If project modules have already been imported, restart the runtime
before loading the updated code. Initial AGENT answers must be generated with
these same descriptions; historical answers using older descriptions cannot
be reused for this experiment.

Questions, evidence packages, costs and generation settings are unchanged.
Historical result files and frozen source archives retain their original values.
The former optical-description variant switch has been retired.

## Reviewer decision update

The active formal notebook uses `evidence-audit-and-selection-2.1`.
It audits the initial answer against labelled modality evidence, retains supported
statements and grounded proposals, and selects the final evidence package.
KEEP also generates a revised answer. See [Evidence revision](evidence_revision_v2.md).

Baseline and revision records share the run label
`heldout-evidence-revision-v21-001` and the same target directory.
Historical results retain their original descriptions and protocol.
