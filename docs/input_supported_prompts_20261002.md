# Concise current-input-supported prompts

Both prompt constants are maintained in src/autonomous_modality/development_inputs.py:
answer policy english-ap-input-supported-1.0 and selector alignment
selector-ap-input-supported-1.0. The iterative prompt is now
bounded-evidence-selector-ap-1.5-input-supported; older traces remain readable.

A prioritizes tests feasible with delivered representations, allowing later
computation. P prioritizes plausible feature-linked explanations without requiring
proof. Additional scientific data requirements are explicitly separated. No idea
quota, composite score or desired condition ranking is introduced.

Keep the working Colab notebook, including its repetition_penalty wiring. This
update changes prompts and versions only, not decoding, token budgets or assets.
Pull the project before importing modules. In an already running session, reload
development_inputs before iterative, then rerun configuration and subsequent cells.
Remove local prompt overrides if the repository is to be the source of truth.
Use a fresh RUN_LABEL and verify the printed versions and saved configuration.
Updating a .py file alone does not replace already imported Python variables.

For a selector-version comparison, both versions must share the new answer policy,
data and decoding. Comparisons against historical answers remain exploratory.
