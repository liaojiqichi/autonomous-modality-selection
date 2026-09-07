# Solution-richness annotation guide

Guide version: `richness-annotation-guide-1.1`  
Counting rule: `solution-richness-counts-1.1`

This is an initial rubric for expert review, not a validated scientific metric.
All examples below are illustrative text, not observations, downloaded data, or
results produced by this prototype. Unit-test annotations are fixtures only.

## What is counted

The primary outcomes remain richness counts, independently of scientific validity
and evidence fidelity. Do not silently filter counts into "correct supported answers".
Record quality findings separately. An executable proposed approach can contribute
without completed numerical analysis. Label proposals, hypotheses and performed
analyses in reviewer notes. Also distinguish proposed cross-modal investigations
from relationships actually derived from the supplied evidence; do not present a
suggestion in a no-data answer as an observed multimodal finding.

- **Analytical approach:** a distinct investigation or operation, such as
  measuring crater depth-to-diameter ratio or comparing ejecta morphology.
  Restating the same operation is not a new approach.
- **Explanatory perspective:** a distinct lens for explaining a result, such as
  impact conditions versus target properties. A longer description of the same
  perspective does not automatically add a perspective.
- **Cross-modal insight:** a statement explicitly relating at least two
  scientific input modalities. Multiple representations of one modality, such
  as a hillshade and an elevation profile, are not two scientific modalities.

Annotate the solution itself, not the selector's `expected_richness`. A predicted
opportunity is not an observed improvement in a generated answer. Counts describe
annotated content; they do not certify scientific truth or evidence availability.

## Cross-modal levels: examples and boundaries

| Level | Weight | Illustrative example | Boundary / counterexample |
| --- | --- | --- | --- |
| `JUXTAPOSITION` | 0 | "An optical image is available, and a topographic profile is available." | Listing both sources does not identify a relationship. Do not award correspondence merely for naming two modalities. |
| `CORRESPONDENCE` | 1 | "The bright arc in the image follows a ridge in the topographic profile." | This states an explicit relationship. "The image and profile are useful" does not. A correspondence alone is not yet a new explanation. |
| `SYNTHESIS` | 2 | "To test whether the bright arc reflects relief rather than albedo, compare its image position with elevation and slope; neither input alone supports that comparison." | The two modalities jointly enable a specific investigation. "Both inputs prove an impact origin" without a supported reasoning link is not sufficient evidence of synthesis. |

For each proposed insight, identify which modalities contribute and what each
contributes. A question, hypothesis, or proposed investigation may be useful
without being an established observation: preserve that distinction in the
description and reviewer notes. A statement calling itself "synthesis" is not
enough to earn that label.

## Duplicate and disagreement handling

1. Record one entry per distinct contribution, not per sentence or mention.
   Group paraphrases manually before scoring. Do not use the model's verbosity
   as evidence of greater richness.
2. Automated approach/perspective counting ignores case and leading/trailing
   whitespace, as before. It does not recognize synonymous phrases.
3. Automated cross-modal counting now uses the modality **set**, description
   after case folding and trimming, and integration **level** together as the
   identity. Reversing the order of modalities does not create a new entry.
   Repeating one synthesis entry three times still produces a score of 2.
4. The same modality pair can support several genuinely different insights;
   do not collapse all statements from that pair into a single item.
5. Different descriptions, modality sets, or levels are not automatically merged.
   In particular, resolve contradictory levels for the same statement manually
   before scoring; the counter does not choose a level or adjudicate disputes.
   Changing the modality label is not a valid way to manufacture new insights.
6. Keep original annotations and reviewer decisions. Calculation does not mutate
   the source annotation. Keep different annotators' records separate rather than
   pooling them and counting repeated statements across annotators.

## Review checklist

- Is this an actual solution annotation, or a clearly labelled illustrative fixture?
- Are analytical approaches, explanatory perspectives, and cross-modal insights
  separated, with paraphrases grouped consistently?
- Do the named modalities reflect scientific sources, not alternative renderings?
- Does each nonzero cross-modal entry state a concrete relationship or joint
  investigation, rather than only listing inputs?
- Are observations, hypotheses, and proposed tests distinguished, with evidence
  limitations noted and unsupported assertions not promoted to established facts?
- Have duplicate entries and conflicting integration levels been reviewed?
- Are expert 1-5 ratings kept separate from the counts? Do not sum them into the
  weighted cross-modal score. Rating anchors require a separate expert pilot.
- Are scenario, solution, annotator, rubric version, and counting-rule version
  retained for reproducibility? With the current annotation schema, the rubric
  version can be recorded in `notes`; do not invent an unsupported input field.

## Compatibility and interpretation

The weights remain 0 for juxtaposition, 1 for correspondence, and 2 for synthesis.
New score outputs carry `rule_version="solution-richness-counts-1.1"`. Legacy
scores without a version remain readable but their rule version is unknown.
Do not silently relabel them as newly calculated results. Duplicate-containing
annotations can produce lower scores under the new rule; preserve old outputs
and explicitly record any recomputation.

This guide borrows the emphasis on clear definitions and reproducible reporting
from [Howcroft et al. (2020)](https://aclanthology.org/2020.inlg-1.23/). The specific
three-dimensional rubric and weights are project conventions, not validated
weights supplied by that paper. Data-identity notices follow the transparency
principle of [Datasheets for Datasets](https://arxiv.org/abs/1803.09010), without
claiming that metadata-only fixtures are scientific observations.
