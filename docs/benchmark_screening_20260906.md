# Review of twelve cases and the first standardized input packages

> English translation of the historical report at commit `3b91476`.
> Review dates, decisions and test counts describe the original work.

This stage completed technical checks of real data, assistant visual screening, four fixed research questions and the first input packages. No project LLM calls, scientific answers or expert scores were produced. Existing source data and historical runs were unchanged.

## Meaning of the review

A provisional pass permits exploratory work within documented limits. Expert approval, precise registration and scientific correctness remain unestablished. A hold indicates that current material is insufficient for inclusion in the initial clearer-boundary development set. Weak rims, smoothed elevation or asymmetric profiles are insufficient on their own to identify a geological process.

Technical checks covered all twelve cases:

- Identity, size and SHA-256 of four acquired source files; derived-raster consistency with the original run.
- Consistent target identity across catalogue, case record and source run.
- Recorded target-centred projection, extent, square pixels, units and scaling for three rasters.
- Recomputed valid-pixel coverage against a 95% threshold; rejection of constant rasters.
- Recomputed central east-west DEM profile, compared with CSV coordinates and elevations.
- Readable previews and pinned checksums for all evidence, overviews and case records.

The assistant inspected each local/context-image and profile overview, plus the separate elevation map. These were qualitative judgments without rim tracing, centre-offset measurements or source-feature registration. All cases still require planetary-science expert review.

## Case-level decisions

| Case | Initial status | Observation and rationale |
| --- | --- | --- |
| Nampeyo | Provisional pass | Discernible rim, interior and corresponding depression; coarse-scale exploration only |
| Echegaray | Hold | Weak image boundary; main DEM depression south of the catalogue point; review the centre |
| Thoreau | Provisional pass | Discernible boundary and central depression; east-west background differences support an asymmetry investigation |
| Bartok | Hold | Incomplete boundary; candidate image boundaries are difficult to match to DEM depression extent |
| Soseki | Provisional pass | Interior, neighbouring craters and coarse topography can be compared; illumination remains a limitation |
| Kenko | Hold | Low contrast and strong brightness texture hinder consistent rim tracing |
| Harunobu | Hold | A prominent mosaic seam crosses the target and may confound morphology interpretation |
| Mofolo | Provisional pass | Broad annular boundary and topography can be compared; interior small craters and texture require caution |
| Eminescu | Provisional pass | Clear boundary and internal structures support comparison with central topography |
| Scarlatti | Provisional pass | Internal and external structures are discernible; bright arcs cannot be equated with elevation peaks |
| Holbein | Hold | Adjacent or overlapping structures leave the complete target boundary ambiguous |
| Giotto | Provisional pass | Large-scale target and depression are discernible; small bright patches cannot establish composition or age |

All twelve cases passed technical checks; minimum valid-pixel coverage was approximately 99.654%. Visual screening yielded seven provisional passes and five holds. Held cases remain in the audit table and original sample count. This development set favours clearer boundaries and cannot provide an unbiased estimate across all Mercury craters.

## Four fixed questions

Every accepted case used identical templates with only the target name substituted. Wording and answer requirements were frozen as `mercury-questions-1.0`. The maintained English edition in `configs/mercury_questions_v1.json` is `mercury-questions-1.0-en.1`; archived run copies remain unchanged.

| ID | Research question | Main constraint |
| --- | --- | --- |
| Q1 | How can rim continuity, floor morphology and internal structures be investigated? | Distinct executable methods; catalogue codes do not supply the answer |
| Q2 | How can east-west topographic asymmetry be tested and separated from regional slope? | Profile relief is not crater depth; acknowledge missing topography |
| Q3 | How can spatial correspondence between image structures and elevation changes be tested? | Distinguish registration, resolution and possible geomorphic differences |
| Q4 | How can local and regional context support testable modification hypotheses? | Specify supporting and contradictory evidence, alternatives and evidence gaps |

These questions invite scientific investigation without a predetermined geological answer or uniquely correct modality pair. Case-review explanations are excluded from selection requests and must not serve as answer ground truth.

## Input packages

Output directory: `experiments/benchmarks/mercury-screened-v1-20260906/`.

- `audit.json`: all twelve statuses, reasons, checks, provenance and code hashes.
- `visual_reviews.json`: frozen assistant screening, explicitly distinct from expert certification.
- `questions.json`: four fixed questions and common answer requirements.
- Per-case `package.json`: target identity, modalities, representations, limitations, units, provenance and file hashes.
- Per-case `evidence/`: catalogue record, two numeric images and previews, numeric DEM and preview, and numeric east-west profile; eight files in total.
- Per-case records such as `Q1-budget-3.json`: structured selection request, rule result and a manifest restricted to selected modalities.

Seven input packages and 28 case–question scenarios produced 56 preparation records across two budgets. Budgets 3 and 5 used ordinal costs of catalogue 1, imagery 2 and topography 2, without measured token or latency meanings.

`request` supplies selection metadata; `selected_files` identifies accessible evidence. Paths are relative to the case directory. Each file records size, SHA-256, units, scientific modality, representation, source ID and parent relationships where applicable. A model adapter must load only the selected manifest. Numeric GeoTIFFs preserve scientific provenance; they still require a suitable model representation.

The mixed optical/profile `overview.png` was reserved for review and excluded from model evidence to prevent modality leakage. Review judgments remain in the audit layer. Every `quality_score` is unknown; none was fabricated.

Each case directory can be relocated and checked with `verify_package()`. Source receipts describe the external archive; approximately 4.8 GB of global data were not copied into these packages. Moving the complete benchmark directory also preserves question, review and source documentation.

## Reproduction and verification

With the optional `pilot` dependencies installed, choose a new output directory:

```powershell
$env:MPLCONFIGDIR = "$PWD/.cache/matplotlib"
.\.venv\Scripts\python.exe -m autonomous_modality.benchmark `
  --run experiments/runs/mercury-real-pilot-20260905/run.json `
  --sources data/acquired/mercury-pilot-20260905 `
  --reviews configs/mercury_visual_reviews_v1.json `
  --questions configs/mercury_questions_v1.json `
  --output experiments/benchmarks/mercury-screened-v1-repeat
```

The builder refuses existing outputs. Visual records are pinned to the source-run hash and cannot automatically approve uninspected cases. Unit tests use explicitly synthetic rasters and cover invalid inputs, hold decisions, tampering, relocation and modality isolation.

Historical final verification: 125 offline tests passed, with lint and format checks passing. All 56 evidence files (302,840,011 bytes) and 56 preparation records were reverified. Third-party raster deprecation warnings did not affect results. The audit pins original configuration hashes; reserialized output copies may differ in formatting.

## Historical next steps

Domain experts were asked to review the seven provisional passes and decide whether the five held cases needed additional data or continued exclusion. Fixed answer settings and evaluation rules were then needed before model inference and blind comparison. This report did not establish improved answer richness or agent superiority. Current work follows `primary_experiments.md`.
