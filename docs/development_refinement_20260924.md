# Development revision: inventory, compact actions and concise answers

This revision responds to the inspected Eminescu development run, which contained
36 attempts: 31 successful, four truncated and one invalid selector JSON response.
Those results remain unchanged. This document specifies the next development run;
offline tests do not demonstrate improved model performance.

## Changes

1. Both one-shot and iterative selectors receive the same field inventory. The
   catalogue exposes id, name, latitude, longitude, diameter and historical morphology
   codes. It supplies no crater depth, relative/absolute age, composition or regional
   population. Optical inputs are two plotted views. Topography is an elevation
   view, two profile plots and sampled numeric text. Full raster processing requires
   additional tools. Inventory metadata contain no target-specific evidence values.
2. A new acquisition response contains action, modality and one short reason:

   ```json
   {"action":"REQUEST_MODALITY","modality":"OPTICAL_IMAGE","reason":"Inspect rim continuity beyond the sampled elevation profiles."}
   ```

   A stop response contains action and reason:

   ```json
   {"action":"FINISH","reason":"The acquired evidence is sufficient for the proposed investigation."}
   ```

   The reason limit is 240 characters. New responses reject obsolete or extra
   fields. Invalid JSON is saved without repair or retry. Legacy trace readers
   remain available.
3. All five conditions use the same concise English answer policy: aim for
   200-300 words, merge overlapping ideas, express each once and end after covering
   them. There is no fixed idea count, new repetition penalty or automatic
   truncation/post-editing. Greedy decoding and the 1024-token answer cap remain fixed.

## Versioned settings

| Component | Current version |
| --- | --- |
| Inventory | mercury-development-contents-1.0 |
| Selector prompt | bounded-evidence-selector-ap-1.2-compact |
| Iterative trace | iterative-selection-1.1 |
| Shared answer policy | english-ap-concise-1.0 |
| Notebook attempt | colab-ap-agentic-development-en-5 |
| Suggested fresh run label | emin-agentic-en-002 |

Two acquisitions, one observation-informed revision, cumulative costs, explicit
FINISH and separate system stops are unchanged. Scientific files stay read-only.
The one-shot condition retains its historical acquisition semantics.

## Colab development check

Use the updated notebook and matching project modules. Save any notebook edits
before refreshing the repository. Restart the runtime if old modules were already
imported; load one model instance and run the updated cells in order.
Choose a fresh RUN_LABEL and verify CASE_DIR. Existing scientific data are reused.
The new inventory and answer policy versions, text and code hashes are recorded
in run metadata. Retain earlier run directories and their failed/truncated records.

Run all four questions and five conditions, producing 36 attempts per crater/model.
The preflight is only a technical smoke test. It cannot confirm response quality.
Do not alter settings partway through the run or retry only failed conditions.

Review the following before freezing a protocol:

- JSON validity and raw failure text; no repaired outputs counted as original successes.
- Whether reasons rely only on fields actually available in the chosen package.
- Actual acquisition order, cumulative cost and agent FINISH versus system stops.
- Completion status, output tokens, approximate whitespace word counts and repeated
  paragraphs. These descriptive checks are not A/P scores or semantic deduplication.
- Separate A/P annotation and scientific-validity/evidence-fidelity review, including
  executable proposals that were not performed.

The summary's exact-paragraph diagnostic ignores case, whitespace and leading
numbered idea labels. It can miss paraphrases, within-paragraph repetition and
formatting variants. It never rewrites the answer or changes completion status.
Compare repeated sampled subsets with care: identical deterministic answers are
not independent evidence of an agent effect.

Changes are bundled in this development revision. A before/after comparison cannot
attribute any improvement to one change alone. A formal attribution study would
require separately versioned ablations with matched conditions. No reduction in
repetition, JSON errors or unsupported expectations is claimed before real inference.
