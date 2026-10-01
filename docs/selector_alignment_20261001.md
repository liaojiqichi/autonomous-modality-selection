# Development selector A/P alignment

Version: selector-ap-alignment-1.0. Iterative prompt: bounded-evidence-selector-ap-1.4-aligned.

Both selectors now share operational A/P definitions and compare the incremental
contribution of feasible evidence choices. The second acquisition distinguishes
new approaches or explanations from corroboration of an existing direction.
Future executable proposals can contribute A. A/P remain separate: no quota,
combined score, preferred modality, or scientifically unsupported capability is added.

The notebook forwards each scenario's answer_requirements to both selectors and
the answer generator. CraterQuestion accepts an optional answer_requirements list;
historical records without it remain readable. Existing action schemas, function
signatures, cumulative costs, acquisition limits and answer policy are unchanged.

Use the updated notebook and matching package together in Colab, with a fresh
RUN_LABEL. Run on development scenarios before freezing a new evaluation protocol.
Preserve previous results. This prompt intervention is not a demonstrated improvement;
compare versions with the same evidence, questions, model and decoding settings.
Do not tune specifically to the best Eminescu combinations or change annotation
boundaries to favor the new selector. No model inference was performed locally.
