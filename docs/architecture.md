# Architecture

```text
CraterQuestion + DataAssetProfile[] + InputSelectionConstraints
                            |
                            v
                 Candidate feasibility filter
                            |
                            v
             Richness-oriented modality selector
                            |
                            v
                  InputSelectionDecision
         /                  |                    \
 analytical approaches  explanatory views  cross-modal insights
                            |
                            v
          future data preparation + Qwen3-VL solution
                            |
                            v
              SolutionRichnessAnnotation
                            |
                            v
                     RichnessScores
```

The deterministic selector is a baseline, not the thesis result. It filters
unavailable or prohibited assets and greedily selects a budget-feasible set using
question-type scores, declared asset capabilities, and pairwise complementarity.

Under selection rule `input-richness-baseline-1.1`, successful greedy selections
are unchanged. If a cross-modal task finishes with fewer than two modalities,
the selector enumerates combinations of the already-filtered assets. It searches
by increasing size (from two to the configured maximum), then lexicographically
by the closed taxonomy's declaration order:

1. `OPTICAL_IMAGE`
2. `CRATER_CATALOG`
3. `TOPOGRAPHY`
4. `SCIENTIFIC_LITERATURE`
5. `SIMULATION_OUTPUT`

The first combination containing all required modalities and fitting the budget
is returned, with required modalities listed first. This ordering is deterministic
and independent of the input asset order. Unavailable and forbidden assets cannot
re-enter through this path. If no combination exists, the cross-modal minimum
error remains. The fallback need not exhaust the budget or modality limit.

With five modalities and at most one asset per modality, the complete space has
31 nonempty subsets (the cross-modal fallback considers only sizes of at least
two). This scope makes enumeration inexpensive without adding dependencies.
No new scientific utility function is introduced. Neither the fallback nor the
existing fixed scores prove that the selected set maximizes measured richness.
Recovered decisions carry `CROSS_MODAL_FEASIBILITY_FALLBACK` and an explicit
feasibility-only rationale; result and candidate records carry the updated
selection rule version.

Evaluation rule `solution-richness-counts-1.1` deduplicates cross-modal entries by
`(modality set, trimmed/case-folded description, integration level)` before
counting, without editing the annotation. Approach/perspective counting and
0/1/2 cross-modal weights remain unchanged. See the
[annotation guide](richness_annotation.md) for the manual review boundary.

`RichnessScores` now has an optional `rule_version`. New calculations set it
explicitly; missing versions in legacy payloads remain unknown (`None`). Legacy
annotations remain readable and may be rescored without overwriting the original
record. Strict consumers of the old score-output shape must be updated before
reading new version-tagged outputs. Input, asset, and annotation schemas remain
at version 2.0; no new required input fields were added.

Demo assets retain metadata-only notices in their existing `limitations` field.
`CASE_SPECIFIC` is a case-level verification requirement, not evidence of data
acquisition. Source and quality fields remain unknown where unverified. No data
adapter, download, raw-data processing, prompt, or LLM call was introduced by
that metadata-notice change.

The optional [real-data pilot](real_data_pilot.md) now adds explicit acquisition
and offline preparation entry points. It uses a separate versioned run contract
and real derived assets, while the metadata-only demo remains separate. Source
files under `data/acquired/` are never overwritten by the preparation adapter;
`data/raw/` remains untouched. The pilot exercises the existing selector and
does not introduce LLM calls or expert richness results.

Schema version 2.0 intentionally replaces the earlier output-presentation model.
It does not retain chart, table, or text output modalities because those are no
longer the object of selection.
