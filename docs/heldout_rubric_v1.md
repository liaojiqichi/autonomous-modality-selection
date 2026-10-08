# Held-out A/P rubric: input-supported-ap-1.0

Freeze before held-out answer generation. Calibrate implementation and evaluator
settings on development answers. Report A and P separately, without a C score
or A+P composite. Annotators retain original answer text and exact source spans.

## Units and duplicate boundaries

A is a distinct concrete analytical test or approach. Routine steps in one workflow,
synonyms and algorithm-name substitutions are grouped together. An executable
proposal may count without being performed. Identify the inputs required to carry
it out. A plot alone is not an executed geological measurement.

P is a distinct mechanism or alternative explanation anchored to a specific feature,
relationship or representation limitation. A morphology label or a list of mechanism
names without an explanatory connection does not qualify. Broad and specific versions
of the same explanation are one group unless different explanatory predictions are
stated. Methodological explanations may qualify when they explain a relevant discrepancy.

Give each separable unit one primary dimension and a within-answer duplicate group.
A passage may contribute both dimensions only where distinct method and explanatory
content can be separated. Do not count observations or modality lists as ideas alone.

## Input support and independent quality

For every relevant deduplicated unit record input support as:

- supported: the supplied evidence and representation enable the proposed test or
  anchor the explanatory perspective; subsequent computation is allowed;
- additional_data_required: an essential scientific input or full raster is absent;
- unclear: the available evidence does not resolve feasibility or anchoring.

Report input-supported A/P as primary counts and all relevant deduplicated A/P as
secondary counts. Report additional-data and unclear groups. NO_DATA uses the same
rules: topic-relevant generic proposals can enter raw counts, but target-dependent
claims need actual supplied support. Do not impose an expected ordering of conditions.

Record scientific validity and evidence fidelity independently: supported/plausible,
problematic or uncertain, with a note. Input support describes access and feasibility;
scientific validity assesses reasoning and evidence fidelity assesses accurate use of
the supplied information. Never silently remove an otherwise counted unit solely to
improve a condition ranking. Report quality-stratified diagnostics separately.

Distinguish proposed, observed and executed statements. A future analysis is proposed;
a claim about visible evidence is observed; executed requires evidence that the stated
analysis was performed. Unsupported measurement claims receive a fidelity warning.

## Procedure

Hide condition, generator identity and selector rationale during initial richness
annotation. Supply only actually available evidence for support and quality review.
Record raw evaluator outputs, version, source spans, normalized descriptions, primary
dimension, duplicate groups, support status, statement status and quality judgments.
LLM assessment is not independent human agreement. Mark unresolved cases explicitly.

Use the fixed 64 primary human-review slots selected before seeing answers. Report
unavailable slots when generation fails; do not replace them using outcome-based choices.
At most 16 additional diagnostic cases may be reviewed separately. Failed generations
are not zero scores. Report truncation, missingness and the number of usable pairs.
