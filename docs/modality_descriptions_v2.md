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

The formal answer-revision notebook now uses reviewer prompt
`answer-revision-evidence-retention-1.1`. It asks the reviewer to distinguish
misused available evidence, evidence supplied by another package, and information
unavailable from every package. Before replacing inputs, it checks what the
complete replacement loses as well as what it adds. KEEP returns the original
answer unchanged and does not certify its quality.

The KEEP/RESELECT schema, costs, initial selector, answer policy and model settings
are unchanged. The default baseline and revision labels are now
`heldout-revision-baselines-retention-v1-001` and
`heldout-answer-revision-retention-v1-001`. Open the updated formal notebook and
run setup in order. Preserve existing runs under their original labels.
This is a prompt intervention; semantic compliance and improvement require model
experiments and are not guaranteed by offline tests.
