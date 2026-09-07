# Primary experiment protocol

Version: richness-four-conditions-1.0, 2026-09-07.

The thesis follows proposal-1.2: AI input selection and three separate richness
outcomes. Caloris quantitative inversion is removed from active work. Its former
source module, tests, active configuration and dedicated documentation were removed.
Original acquired products and experiments/research/ records remain historical,
outside the primary evaluation; their protocol snapshots allow recovery of context.

Use four primary conditions: NO_DATA, ALL_AVAILABLE, RANDOM, AGENT. Random sampling
is uniform over nonempty feasible subsets in stable asset-ID order, with a recorded
seed. Random and agent share constraints. ALL_AVAILABLE ignores budget/count caps
and reports its cost separately, but respects prohibitions and confirmed availability.
CASE_SPECIFIC is excluded until verified. NO_DATA intentionally uses empty evidence.
Question types do not force evidence pairs in these primary conditions.

AGENT is pending, never replaced by a rule decision. This release performs no model
calls or answer generation. Infeasible selections are persisted separately from
intentional no-data controls. Units are engineering cost units, not inference costs.

```powershell
.venv\Scripts\python.exe -m autonomous_modality.experiments `
  --benchmark experiments/benchmarks/mercury-screened-v2-20260907 `
  --questions configs/mercury_questions_v1.json `
  --output experiments/primary/mercury-four-conditions-repeat `
  --budget 3 --seed 42
```

Output must be new. Existing package evidence is hash-verified, not copied or
rewritten. Output references use absolute paths; relocation requires re-preparation.
The record contains provenance and a separate answer_input whitelist. A future
generator must consume only that whitelist, never the entire preparation record.
This is input routing, not yet an implemented model/tool filesystem sandbox.

Q1–Q4 from the original version are the active pilot questions. They deliberately
target scientific investigation methods; some mention specific modalities, so
generalization to less leading questions needs a later expert question pilot.
They require neither parameter inversion nor completed numerical analyses.
The historical Q5–Q7, quantitative readiness fields, budget trials and fixed-pair
runner remain legacy/auxiliary compatibility paths and are not primary experiments.
The new runner rejects question sets carrying quantitative inversion prerequisites.

Primary metrics remain the counts/diversity of approaches, perspectives and
cross-modal insights. Proposed executable approaches can count without execution.
Quality checks and evidence fidelity are separate outcomes, never silent filters
on the primary richness counts. See richness_annotation.md.

Next: agree model phase/budget, implement an actual selector and generator, fix
representation/output policies, run a small blinded annotation pilot, then freeze
the formal target split and repeat schedule. Preparations are not answer results.

## Verified preparation, 2026-09-07

The final run is experiments/primary/mercury-four-conditions-20260907-final/preparation.json.
Seven existing provisionally screened targets × four original questions × four
conditions = 112 records. Each condition has 28 records: no-data, all-available
and random are ready for later generation; agent is pending. No answers were
generated. Seed 42, budget 3, maximum modalities 3. Final offline tests: 139 passed;
Ruff lint and formatting passed. The 117 warnings originate in Rasterio/Affine.
