# Code review and next milestones — 2026-09-06

> Historical review. Its roadmap is superseded by proposal-1.2 and primary_experiments.md.

## Scope and confirmed fixes

Reviewed the domain models, deterministic selector, richness-count evaluation,
metadata demo, source acquisition, raster preparation, pilot reporting, tests and
configuration. No LLM integration or additional data acquisition was performed.
Existing sources and historical experiment artifacts are preserved.

| Issue | Correction | Compatibility impact |
| --- | --- | --- |
| Arbitrary demo crater names inherited Caloris coordinates | Demo explicitly accepts Caloris only | Previously misleading non-Caloris invocations now fail |
| Repeated capability labels inflated base scores | Trim/case-fold deduplication before scoring and expected-richness reporting | Selection rule 1.2; inputs without duplicates retain their scores |
| Some numeric inputs accepted infinity; asset IDs could collide | Reject non-finite values and duplicate asset IDs | Invalid inputs now fail validation |
| Duplicate CSV headers could overwrite values silently | Validate column count as well as names | Malformed catalogues now fail |
| Source receipts depended on old absolute paths; duplicate receipts collapsed into a dictionary | Centralized local source resolution, pinned identity, size/hash checks and duplicate detection | Receipts are not rewritten |
| Receipt byte count could contradict pinned size | Cross-field validation | Inconsistent receipts now fail |
| Cropping assumed metre-based, square, north-up grids without checking | Explicit grid validation; direct adapter also rejects raw-directory outputs | Unsupported grids now fail before derived files are written |
| Infeasible trial aborted the selection batch; failed coverage skipped a whole case | Persist result or error for every selection condition, save case first, disable only affected modality | Pilot/run 1.1, readable legacy 1.0 |
| Repeated source verification and crop-width literals | Reuse source loader and configuration fields | Narrow internal simplification |
| Report used current code version and a fixed DEM scale | Display recorded run version, file-derived scaling description and failed-trial count | Historical report files unchanged |

The deduplication is textual, not semantic. It does not claim that paraphrases
describe independent scientific methods. Existing annotation guidance correctly
keeps semantic overlap and scientific validity under expert review.

## What the project currently establishes

There is a working engineering path from acquired catalogue/imagery/DEM through
derived products and availability metadata to reproducible deterministic
selections. Richness annotations and transparent count metrics are implemented.
The previous 12-crater, 192-trial pilot is an integration experiment, not evidence
of improved scientific answers. Availability and capabilities are mostly
hand-authored; the selector does not interpret actual image content.

## Remaining work, in priority order

1. **Scientific QA and a frozen benchmark.** Review all 12 crater centres,
   catalogue/image alignment, DEM validity and interpretation limits. Persist
   pass/reject/uncertain decisions with reviewer and evidence. Freeze 3–5 initial
   questions, acceptable evidence and rejection criteria; split by crater, not
   merely by differently worded questions about the same crater.
2. **A standard input package.** Separate decision-time metadata from the actual
   selected evidence and its model representation. Add explicit representation
   manifests, quality/coverage status, source links and measured resource costs.
   Check spatial compatibility and required data quality before selection.
   Keep one asset per modality until concrete cases require multiple alternatives.
3. **Model-assisted selection and answer generation.** This requires an explicitly
   agreed next phase because current project instructions prohibit LLM calls.
   Add versioned prompts, a model adapter, strict outputs, timeouts and fallback,
   then generate answers from actual selected evidence with traceable claims.
   Do not put scientific validation only inside prompts.
4. **A fair scientific evaluation.** Compare fixed-rule selection, all available
   inputs, single-modality and simple budget-matched baselines. Keep model and
   answer prompt fixed, repeat runs, and use blinded expert annotations with
   agreement checks. Evaluate factual/evidence quality separately from richness;
   report uncertainty and resource costs, not only counts of selected modalities.
5. **Reproducibility and operation.** Add environment locking and automated checks,
   a replay command, portable derived-product references, checksums for all model
   inputs (including previews/profiles), and resumable preparation with explicit
   case-level failures. Current source checksums prove file integrity, not
   scientific accuracy. Core schema version fields also need explicit supported-
   version validation/migration before external schema versions are accepted.

## Recommended immediate step

Complete a structured QA manifest for the existing 12 cases and define 3–5
representative questions. Then build and validate the standard input package for
those approved cases without calling an LLM. This resolves the largest current
uncertainty—whether inputs actually support the intended questions—before adding
more downloads, model orchestration, training or a user interface.

## Verification

- Python 3.12.14; Ruff lint and formatting checks passed.
- 112 offline tests passed, including optional raster tests. Ten warnings originate
  from rasterio/affine's pending matrix-multiplication deprecation, not test failures.
- Read the historical 1.0 run and replayed all 192 selections across 12 cases with
  the new rule: zero changed decisions and zero failed selections.
- Reverified all four local sources (4,778,972,401 bytes) against receipts. Both
  real raster grids meet the newly explicit projection/pixel-grid requirements.
- No full raster re-preparation was performed; historical crops and reports were
  preserved. The adapter changes were exercised on synthetic rasters.
