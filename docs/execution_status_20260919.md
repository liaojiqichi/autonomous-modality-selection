# Execution status — 19 September 2026

## Completed locally

- Final PDF identified by SHA-256 in configs/experiment_protocol.json.
- A/P-only annotation and scoring replace old C structures and weights.
- Strict source spans, normalized ideas, duplicate groups, statement status and separate
  quality judgments are validated. This is schema/scoring implementation, not LLM annotation.
- Paired model preparation: Qwen3-VL and Gemma 4; 5 RANDOM draws with replacement.
- Budget 4 primary and budget 3 sensitivity; at most two selected modalities.
- Reviewed 6/30 split schema and held-out gates; no split is approved automatically.
- Historical evidence projection reuses 12 original cases without loading obsolete scores.
- Seven current packages verified, producing 448 preparation records per budget:
  experiments/primary/ap-development-20260919-b4/preparation.json
  experiments/primary/ap-development-20260919-b3/preparation.json
- These two files replace only this session's preliminary preparation files. No historical
  run, source raster, catalogue, previous proposal PDF or acquired data was removed.
- Candidate feasibility: 16,876 catalogue rows; 82 named candidates under existing
  geometry constraints (diameter 50–150 km, |latitude| < 45, 15 < |longitude| < 150).
  Excluding 12 historical targets leaves 70 metadata candidates. They have NOT passed
  image/terrain quality review and are not a representative or approved held-out set.

## Verification

Python 3.12.14. Ruff check and format check passed. Full pytest, including evidence-view
extension: 164 passed, 160 Rasterio/Affine pending-deprecation warnings.
Default Windows temporary/cache directories were inaccessible; final tests used:
`python -m pytest --basetemp tmp/checks-ap-20260919-02 -o cache_dir=tmp/cache-ap-20260919`.
For another run choose a fresh temporary path.
No external LLM was called. No answer, annotation or scientific effect estimate was generated.

## Remaining work (not a claim of completion)

1. Screen the expanded candidate pool for coverage, centre alignment and scientific suitability.
   Reuse global rasters and existing extraction functions; save only necessary new crops.
2. Review and freeze six development and thirty independent held-out targets, tracking
   any external/Colab inspection history. The seven current packages form a pool, not a final split.
3. Connect actual model-specific Colab inference to the metadata-only selector and selected
   evidence representations. Freeze checkpoint revisions and input/output settings after
   BOTH models pass GPU compatibility tests. Current Python entry point is preparation only.
4. Implement and exercise persisted generation-attempt logging, failure/truncation handling,
   LLM annotation execution, blind export, human audit sampling and target-level paired analysis.
   The models/schema alone do not implement these execution stages.
5. Run the frozen experiment. No fabricated or simulated output may count as a real result.

No GPU session is connected from this workspace, and no paid compute or GitHub push was
performed. The schedule is advisory; no routine reminder/monitoring automation exists.
