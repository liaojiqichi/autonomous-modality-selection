# Second version: imagery–topography control and scientific interpretation questions

> Historical auxiliary protocol. Use `primary_experiments.md` for current A/P dual-model experiments.
> Quantitative work in Q5–Q7 is outside current thesis deliverables.
> This is an English translation of the historical report at commit `3b91476`; it records no new scientific review or execution.

This stage extended offline preparation. It made no LLM calls, downloaded or fabricated no simulations, and estimated no impact parameters. The first version's 56 records, frozen question copies and source data were preserved.

## Fixed control

The `fixed-image-topography` condition requires both OPTICAL_IMAGE and TOPOGRAPHY, with at most two modalities and budget 4; other modalities are disallowed. Missing required assets produce an explicit error. There is no silent catalogue substitution. Seven imagery and topography files are routed; catalogue files and mixed-modality overviews are excluded.

All second-version conditions share target name and coordinates. CraterReference no longer supplies catalogue diameter. Catalogue diameter and historical classifications are available only through selected catalogue evidence. Asset metadata remain available to the selector; answer generation is restricted to selected evidence. Raster extent may indirectly reveal target scale, so some prior diameter information may remain.

The changed shared-context policy required regenerating budget-3 and budget-5 preparation records. Comparisons should remain within this version. Historical results remain readable and unchanged.

## Additional scientific questions

Q1–Q4 retained their original wording and answer requirements. The historical configuration version was `mercury-questions-2.0`. The maintained English edition is `mercury-questions-2.0-en.1`.

| Question | Scientific objective | Prerequisites for quantitative answers |
| --- | --- | --- |
| Q5: impact-parameter degeneracy | Identify impactor size, velocity, angle and target thermal-state combinations producing similar final diameters; constrain them with morphology | Final diameter and uncertainty, a real simulation grid at an applicable scale, consistent observational and simulation definitions |
| Q6: discriminating additional observations | Compare the additional discriminating value of floor relief, rim geometry and internal structures for models matching diameter | Candidate predictions, reproducible feature measurements and uncertainties, predefined acceptance criteria |
| Q7: competing explanations for shallowness | Once shallowness is established, distinguish infilling, relaxation, background slope and measurement bias | Reliable depth definition and measurement, matched reference craters, applicable forward models and literature |

These are target-specific research designs. They do not establish that all seven targets are large basins or unusually shallow. Q5 explicitly prohibits directly transferring Caloris parameters. A Caloris analysis would require a separate basin case with reviewed observations and simulations.

The historical design drew on the previously checked [Caloris SPH study](https://arxiv.org/abs/2608.26957), moving from basin size alone to multiple observational constraints. Q5–Q7 were formulated by this project; the paper did not supply their answers or simulation assets.

## Quantitative readiness

Preparation records add:

- `condition`: distinguishes free budget-constrained selection from the fixed pair.
- `missing_quantitative_modalities`: modalities needed for the full quantitative task but not selected.
- `unverified_quantitative_prerequisites`: unverified measurements, parameter grids, uncertainty models and related requirements.
- `quantitative_status`: `not_ready` indicates unmet requirements; `not_assessed` indicates that this review has not been performed.

Checks operate independently of question wording. All prerequisites for the new questions remain unverified, so every Q5–Q7 record is `not_ready`. These questions can still test proposals for analysis, recognition of missing evidence and acknowledgment that specific parameter estimates are unavailable. Rule scores do not perform physical inversion or automatic information-gain estimation.

A complete Q7 investigation may require more than the three modalities permitted in the historical single selection. The record documents this gap; a complete execution would require a later multistage workflow.

## Outputs and reproduction

Directory: `experiments/benchmarks/mercury-screened-v2-20260907/`.

Seven screened cases × seven questions × three conditions produced 147 preparation records, including 49 fixed-pair controls and 63 additional-question records. All 63 were quantitatively unready. Preparation records contain no generated answers and do not constitute 147 independent scientific samples.

```powershell
$env:MPLCONFIGDIR = "$PWD/.cache/matplotlib"
.\.venv\Scripts\python.exe -m autonomous_modality.benchmark `
  --run experiments/runs/mercury-real-pilot-20260905/run.json `
  --sources data/acquired/mercury-pilot-20260905 `
  --reviews configs/mercury_visual_reviews_v1.json `
  --questions configs/mercury_questions_v2.json `
  --output experiments/benchmarks/mercury-screened-v2-repeat
```

The output directory must be new. Technical checks are rerun for all twelve existing cases. Reused assistant-screening records retain their original date and `provisional_pass` status for limited exploratory use.

## Historical next empirical step

For Q5/Q6, the proposed next step was to identify a target matching the scale of a published simulation grid, obtain real parameter tables, outputs and applicability documentation, and fix diameter uncertainty, model-acceptance tolerances and additional-observation definitions before screening. Those assets were unavailable, so the project could not identify excluded impact-parameter combinations. This quantitative extension remains outside current A/P thesis deliverables.
