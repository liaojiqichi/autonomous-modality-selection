# Autonomous Input Modality Selection

Full research plan: [研究计划书 / Proposal](docs/research_proposal.md).

Colab setup: [private code repository and independent downloads](docs/colab_setup.md).

Master's thesis prototype for selecting scientific input data modalities for
Mercury crater questions. The research outcome is **solution richness**, defined
along three dimensions:

1. diversity of analytical approaches;
2. diversity of explanatory perspectives;
3. cross-modal insights.

The current implementation is deterministic and does not call an LLM. It models
available scientific assets, filters infeasible inputs, selects a budget-limited
modality combination, predicts its richness contributions, and represents expert
richness annotations.

## Requirements and installation

The active [four-condition protocol](docs/primary_experiments.md) prepares no-data,
all-available, random and pending-agent conditions from verified evidence packages.
Caloris quantitative inversion is outside the thesis scope. Acquired data and
historical runs remain archived; they are not primary answer evaluation results.
Install optional preparation dependencies with `python -m pip install -e ".[dev,pilot]"`.

- Python 3.12+

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Verification

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

## Current input modalities

- `OPTICAL_IMAGE`
- `CRATER_CATALOG`
- `TOPOGRAPHY`
- `SCIENTIFIC_LITERATURE`
- `SIMULATION_OUTPUT`

Scientific modality and model representation are kept separate. For example,
topography is a scientific modality, while hillshade and elevation profiles are
two possible model-compatible representations of that modality.

## Demo

The demo uses metadata describing candidate assets. Placeholder assets are
explicitly marked as case-specific or unavailable; it does not fabricate or
claim to load scientific observations.

```powershell
.\.venv\Scripts\ams-demo.exe `
  --question "What approaches could investigate the formation of Caloris?" `
  --question-type ANALYTICAL_APPROACH_DISCOVERY `
  --crater-name Caloris `
  --maximum-modalities 3
```

The JSON output contains candidate assets, structured exclusions, scores,
selected modalities, expected analytical approaches, expected explanatory
perspectives, anticipated cross-modal insights, and total cost.

Every demo asset carries a metadata-only notice in `limitations`, including
assets declared `AVAILABLE`. The candidate records in the JSON output retain
these notices; selected entries refer to them by `asset_id`. Availability is a
declared selection assumption, not proof that a product has been acquired.
`CASE_SPECIFIC` requires verification for the particular target and use case.
Unknown `source_uri` and `quality_score` values stay `null`; no source or quality
is inferred from a product title. Existing availability filtering is unchanged.

## Selection fallback

Current rule `input-richness-baseline-1.2` deduplicates trimmed, case-folded
capability descriptions before scoring and reporting expected contributions.
Repeating a capability no longer increases its score. Semantic paraphrases are
not automatically merged. The metadata-only demo accepts Caloris only because
its coordinates and asset assumptions are specific to that basin.

The fallback introduced in `input-richness-baseline-1.1` preserves successful greedy choices,
their ordering, and their costs. Only when a cross-modal task ends with fewer
than two selected modalities does the selector search feasible combinations.
For example, a budget of 2 cannot fund a cost-2 topography asset plus another
positive-cost asset, but can fund a cost-1 image and a cost-1 catalogue together.

The fallback checks filtered assets by increasing combination size, then by the
closed taxonomy's order. It returns the first combination satisfying the required
modalities, total budget, and modality limit. No hard constraint is relaxed.
True infeasibility still raises an error. The decision includes
`CROSS_MODAL_FEASIBILITY_FALLBACK` when recovery was needed.

This is a feasibility safeguard, not an optimizer of solution richness. It does
not change the existing scores, pair bonuses, or predicted-versus-measured
richness distinction. See [architecture](docs/architecture.md) for version notes.
See the [code review and project roadmap](docs/code_review_20260906.md) for the
current implementation boundary, review fixes, and next research milestones.

## Richness evaluation

`SolutionRichnessAnnotation` stores distinct analytical approaches, explanatory
perspectives, and cross-modal statements. Cross-modal statements are classified
as:

- `JUXTAPOSITION`: modalities are merely listed together, weight 0;
- `CORRESPONDENCE`: an explicit relationship is identified, weight 1;
- `SYNTHESIS`: modalities jointly enable a new investigation or explanation,
  weight 2.

`calculate_richness()` produces transparent counts. Expert 1–5 ratings can be
stored separately and are not silently merged with the counts.

Evaluation rule `solution-richness-counts-1.1` counts duplicate cross-modal
entries only once when their modality sets, trimmed/case-folded descriptions,
and integration levels match. Original annotations are not modified. Paraphrases
and inconsistent integration levels still require human review; this function
does not determine semantic equivalence or scientific validity.

New `RichnessScores` outputs include `rule_version`. Older payloads without this
optional field remain readable with `rule_version=None`, meaning unknown, not
recomputed using the new rule. Old strict readers may need updating to accept
the additional output field. Do not compare legacy and new scores without
checking their rules; recompute from preserved annotations when needed.

Use the [richness annotation guide](docs/richness_annotation.md) for definitions,
illustrative examples, duplicate handling, and a short review checklist.

## Project structure

```text
configs/                     Versioned taxonomies and rule documentation
docs/                        Architecture and research documentation
src/autonomous_modality/     Models, baseline selection, evaluation, and CLI
tests/                       Validation, selection, richness, and CLI tests
```

## Primary experiments

```powershell
.venv\Scripts\python.exe -m autonomous_modality.experiments `
  --benchmark experiments/benchmarks/mercury-screened-v2-20260907 `
  --questions configs/mercury_questions_v1.json `
  --output experiments/primary/mercury-four-conditions-repeat `
  --budget 3 --seed 42
```

Use a new output directory. Q1–Q4 are the active pilot questions. The historical
benchmark runner and Q5–Q7 remain for compatibility/auxiliary work only. The active
runner rejects quantitative-inversion prerequisites. Agent selection is pending;
no rules are reported as AI decisions, and no answers are generated in this phase.

## Next steps

1. Agree the model phase, inference budget and expert annotation arrangements.
2. Connect an actual agent selector and a generator consuming only selected evidence.
3. Freeze model representations, shared prompts and output-length policies.
4. Pilot blinded richness annotations and independent validity/fidelity checks.
5. Freeze target-level splits and repeat schedules before formal evaluation.

Data adapters, crops, source receipts and portable input packages already exist.
See [real-data preparation](docs/real_data_pilot.md) for their historical workflow.
