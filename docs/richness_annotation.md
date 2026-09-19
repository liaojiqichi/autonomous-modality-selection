# A/P annotation rubric — richness-ap-1.0

Only two independent counts are reported; do not calculate C or an A+P composite.
A: distinct, concrete executable strategy for analysis/testing.
P: distinct mechanism, hypothesis or alternative explanation relevant to the question.
Methodological alternatives such as sampling bias can be P if they actually explain the observation.

Split answers into minimal independently interpretable units. Each gets one primary
dimension. A passage can supply A and P only if distinct content can be separated.
Routine workflow steps, algorithm-name substitutions, paraphrases and modality lists
are not independent ideas. Use the same duplicate_group for semantic duplicates.
The scorer does NOT infer semantic equivalence; the annotator must supply grouping.

Required records: exact source answer, zero-based half-open character offsets,
normalized description, idea ID, duplicate group, A/P, relevance, proposed/observed/executed
status, scientific validity and evidence fidelity plus notes. Offsets refer to the
unmodified answer; do not strip whitespace. No C labels or cross-modal bonus are accepted.
Unsupported science does not silently become zero richness: quality is reported separately.
Concrete proposed analyses may count even when not executed.

Illustration (not observed planetary evidence): “Compare elevation profiles; regional
tilt could explain the asymmetry.” The comparison can be A and tilt can be P. Using two
modalities does not create an extra score.

LLM annotation uses the versioned rubric, with evaluator checkpoint/configuration
recorded separately. Retain raw outputs and validation errors; never replace invalid
annotations with zero scores. Where feasible evaluate independently with two LLMs.
Hide condition, generator identity and selection rationale during richness annotation;
provide actually supplied evidence for fidelity checks. Answer content can reveal condition.

Human review: 64 prespecified stratified answers, plus up to 16 diagnostic cases kept
separate. Review relevance, duplication, plausibility, evidence use and proposed-versus-
executed distinctions. LLM agreement is not human agreement or proof of correctness.
Calibrate using development answers before freezing the rubric.

Historical three-dimensional annotations are not accepted by this schema. Preserve
their files unchanged; if reannotating, create a new annotation with the A/P rubric.
