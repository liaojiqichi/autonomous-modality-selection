# Held-out four-modality data and design

The current release is `experiments/benchmarks/mercury-heldout-four-modality-v2-20261008`.
It contains 30 targets with complete four-modality evidence, technical reviews,
fixed questions and a versioned scientific design. No model answers or expert
approval are included. Runtime and evaluator approval remain pending.
Existing development data remain unchanged.

## Allocation

The historical Herrick 2011 catalogue is reused with its checksum verified.
The scope follows the existing pilot: named craters, diameter 50-150 km inclusive,
absolute latitude below 45 degrees, and 15 < absolute longitude < 150 degrees.
This restricted population must be stated when reporting generalization.

All twelve previously inspected pilot targets are excluded, including the five
historical holds. Caloris is also excluded. The explicit ID list is versioned in
`heldout.py`; it must be extended if further prior target exposure is identified.

Eligible targets are ranked by SHA-256 of `20261008:<catalogue-id>` and the first
30 are allocated. Remaining targets form an ordered reserve pool. This choice is
a new reproducible implementation policy, not an already approved proposal detail.
Cache coverage and model performance do not influence allocation. Any replacement
requires a recorded data-quality reason and a new allocation version; no silent
replacement or repeated sampling is implemented.

## Offline preparation

```powershell
.venv/Scripts/python.exe -m autonomous_modality.heldout `
  --sources data/acquired/mercury-pilot-20260905 `
  --multispectral-cache data/acquired/mdis-multispectral-v4-20261006 `
  --output experiments/benchmarks/mercury-heldout-candidates-20261008
```

The builder refuses an existing output directory. It verifies source receipts,
reuses the existing 2D local and 5D context cropping implementation, and saves a
catalogue record, optical local/context rasters and previews, DEM and central
east-west profile per target. These are preparation products, not the final
model-facing evidence-view package. The inherited `case.accepted` field means
only that the original core coverage threshold passed.

The complete cached nonpolar MDR label inventory determines required tiles from
each actual context footprint. Cached image checksums are verified and missing
tiles and byte counts are recorded. No network access is attempted. Each target
has a create-only checkpoint; an interrupted run is incomplete and must not be
treated as a completed release.

## Completed preparation and review

The original missing-tile estimate was ten. A signed-longitude wraparound error in
the tile intersection rule was found when Tyagaraya failed coverage. Correct handling
of tiles crossing 180 degrees required three additional tiles (H08NE4, H08SE4 and
H08SW4). All thirteen were acquired in the shared verified cache. The first failed
build and original candidate report are retained as historical preparation records;
the v2 acquisition plan supersedes their incomplete tile inventory. No target was
replaced and no missing reflectance was fabricated.

Each target has eight-band local and context GeoTIFFs, an NPZ spectral cube with
four geometric region masks, statistics, source hashes and a correspondence figure.
There are 60 crops and 120 region masks. Optical local/context views, numeric DEM,
central east-west and south-to-north ordered profiles, and terrain statistics are
retained. The model input uses five images with longest edge 448 pixels, 17 samples
per terrain profile in text, and a four-region eight-band numeric spectral summary.
Spectral review composites, full rasters and review notes are not answer inputs.
The regions are geometric proxies; they are not geological segmentation or mineral labels.

All 30 six-panel correspondence figures and all core contact sheets were directly
inspected by Codex. This is provisional technical visual review, without independent
planetary-science expert approval or measured subpixel registration. Minimum spectral
joint-valid coverage is 99.5103% locally and 99.9214% in context (Mussorgskiy); all
other targets have 100% for both. The fixed threshold is 95%. The missing wedge is
preserved as nodata. Significant optical mosaic seams, bright display clipping,
indistinct boundaries and Bronte's catalogue-center offset are recorded in separate
core/spectral review files. Passing means sufficient technical correspondence for
the bounded input experiment, not suitability for every proposed geological analysis.

The verifier recomputes spectral masks, regional statistics and both DEM profiles,
checks catalogue identity, projected center, source/compact hashes and modality routes.

## Protocol revision approved on 8 October 2026

The user explicitly approved retaining relative costs: catalogue 1; optical,
topography and multispectral 2 each. These are experimental ordinal units, not
measured tokens, time or monetary costs. The main budget is 4 and sensitivity budget
3, with at most two cumulatively accessed modalities and no refunds. ALL_AVAILABLE
receives all four, total ordinal cost 7, and remains a full-evidence reference.

The primary conditions are NO_DATA, ALL_AVAILABLE, RANDOM and AGENT_ITERATIVE.
Historical one-shot AGENT is an auxiliary ablation. The iterative agent has at most
two selector calls/acquisitions and one observation-informed revision; model FINISH
and system-imposed acquisition limits remain distinct in the log. Literature search
is outside this protocol.

The unchanged four English question templates produce 120 scenarios. Five random
draws with replacement are saved per scenario and budget and shared across models.
Budget 4 has ten legal nonempty subsets; budget 3 has seven. No-data/all-data/iterative
each contribute one attempt and RANDOM five: 1,920 primary attempts across two models;
including one-shot AGENT gives 2,160 per budget. No comparison ordering is assumed.

The frozen rubric reports input-supported A and P separately, with raw relevant A/P
as secondary counts and independent scientific-validity/evidence-fidelity checks.
Sixty-four stratified human-review slots are selected without seeing answers. Failed
slots remain unavailable; up to sixteen diagnostic examples are reported separately.
This sample size is a recorded implementation choice, not completed human review.

## Freeze and runtime prerequisites

`release.json` pins all released files. `frozen/protocol.json` records the revision,
costs, condition roles and generation limits; `frozen/design.json` contains expanded
questions, random draws and review slots. Source snapshots and the rubric are included.
The copied notebook is the development reference, not a ready formal-test runner.
Nested candidate/package records retain their original pending/development labels;
the release-level manifest and separate reviews describe their completed QA status.

Verify without network access:

```powershell
.venv/Scripts/python.exe -m autonomous_modality.heldout_finalize `
  experiments/benchmarks/mercury-heldout-four-modality-v2-20261008
```

Before held-out inference, pin both model checkpoint/processor revisions, quantization,
attention implementation and software versions, and verify memory/decoding on development
targets. Implement the formal runner against the frozen draws and compact receipts;
the old development download URL does not deliver this held-out release. Pin evaluator
settings after development-only calibration before annotation. Technical changes that
alter prompts, evidence or limits require a documented new protocol version.

Do not run held-out answers to tune prompts or selectors. Data-quality review is
distinct from development feedback. The release status is
`data_and_design_frozen_runtime_pending`; runtime approval is false.
