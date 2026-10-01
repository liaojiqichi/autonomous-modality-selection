# Development P-boundary clarification: p-boundary-1.1-dev

This is a development calibration supplement to richness-ap-1.0. Historical
annotations remain unchanged. Revised exports retain the base schema and carry
this supplement's identifier in their wrapper and annotation notes. A units and
quality judgments are held fixed to isolate the effect of reviewing P boundaries.

## Uniform inclusion rule

Count a P when the answer connects a distinguishable causal process or source of
error to a specified feature, discrepancy or pattern. The connection may be
conditional, prospective or scientifically questionable. No numerical result,
new observation or sophisticated physical model is required. Read the surrounding
sentence/paragraph, rather than scoring isolated keywords.

- A broad mechanism can count when its role is explicit: regional tilt explaining
  directional profile differences, or illumination explaining apparent brightness.
- A list of process names for unspecified future validation does not count.
- A generic placeholder (independent processes, structural control) contributes no
  extra P beyond a concrete mechanism supplied as its example.
- A restatement of the outcome (a real mismatch explains a discrepancy) does not
  add a causal perspective.
- A rejected hypothesis can count when a particular mechanism is evaluated against
  a specified phenomenon or discriminating observation. A blanket statement such
  as exclude volcanism, without relating it to a feature/process, does not count.
- Different observations or mathematical summaries of one proposed cause do not
  multiply P. An umbrella process and a specifically triggered instance share a
  duplicate group unless the answer develops distinct competing explanations.
- A chronological sequence offered as one history remains one P. Alternative
  mechanisms may form separate P units even when they address the same feature.
- A methodological limitation counts only if it supplies an explanatory alternative
  for a specified apparent pattern; generic requests for better resolution or data
  do not count.

Scientific validity and evidence fidelity remain separate. False projection claims
or unsupported causal inferences may still have sufficient explanatory structure
to count. Removing a name-only unit is a specificity decision, not a quality penalty.

## Review procedure

Review every existing P and reread the complete answers for missed P candidates.
Record keep/drop/merge/add decisions with exact context and machine-readable codes.
Apply the same boundary to NO_DATA, ALL_AVAILABLE, RANDOM, AGENT and AGENT_ITERATIVE.
Deduplication occurs within each answer; independent answers retain separate records.
Use the same revision for identical text after verifying identical supplied inputs.

The 1 October audit is a single AI review, with prior access to condition labels.
It is not blinded or independent rater agreement. Changes must not be interpreted
as a validated new gold standard or a means of improving the agent's ranking.
Before held-out evaluation, adjudicate borderline cases and freeze the rubric.

## Exhaustive development comparison

Use [the development sweep](development_sweep.md) to distinguish selection mistakes
from limits of the answer model/input representations. Report A and P separately,
alongside quality and failures. The maximum among inspected development combinations
is an observed best, not a proven population optimum or an unbiased oracle estimate.
