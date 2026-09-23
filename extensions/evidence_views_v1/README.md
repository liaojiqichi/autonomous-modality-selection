# Opt-in input representations: evidence-views-1.0

This extension reads existing evidence and writes new representation packages. Source data, existing evidence packages and historical notebooks remain unchanged. The builder performs no downloads, LLM calls or dependency installation.

## Outputs

The builder reads `catalogue.json`, `image_local.tif`, `image_context.tif` and `dem_local.tif` from an existing `input-package-1.0` package after checking every source-package file hash. It produces:

- A byte-for-byte catalogue copy, preserving fields and uninterpreted codes.
- Local and context optical images with consistent canvas, coordinate annotations and 0–255 display range.
- A byte-for-byte copy of the numeric DEM.
- An elevation map showing profile positions.
- Fixed east-west and north-south profiles, each with a full CSV and PNG, computed from the existing DEM without modifying the original east-west CSV.
- `terrain_summary.json`: full-crop statistics, coordinates, units, scaling and complete profiles.
- `terrain.txt`: model-visible statistics and, by default, 17 evenly indexed samples per direction. Local extrema may be missed. Missing values are null, with no interpolation across gaps.
- `manifest.json`: source/output SHA-256 hashes, settings, extension-code hashes and dependency versions. It is written last to indicate completion.

For even dimensions, profiles average the two central lines and require both samples to be valid. Odd dimensions use the central line. North-south profiles are ordered south to north. These are raster-centre cross-sections, without expert-traced rim or floor measurements. The elevation range does not measure crater depth. Horizontal distances are relative to the catalogue centre in the source projection; registration errors may remain. All representations still belong to three scientific modalities.

## Run from the project root

Use the existing Python 3.12+ environment with pydantic, numpy, rasterio and matplotlib. The launcher changes only the current process's import path.

```powershell
.venv/Scripts/python.exe extensions/evidence_views_v1/run.py build `
  --source experiments/benchmarks/mercury-screened-v2-20260907/crater-16604 `
  --output experiments/benchmarks/mercury-screened-v2-20260907/representation_trials/evidence-views-v1/crater-16604
```

The output directory must be new. There is no overwrite option. Failure may leave an incomplete directory without `manifest.json`; the adapter will reject it. Retry in a new directory, and inspect incomplete output before manually removing it.

```powershell
.venv/Scripts/python.exe extensions/evidence_views_v1/run.py preview `
  --package experiments/benchmarks/mercury-screened-v2-20260907/representation_trials/evidence-views-v1/crater-16604 `
  --question "How could we investigate terrain asymmetry?" `
  --selected TOPOGRAPHY
```

`preview` prints model inputs without generating an answer. NO_DATA uses an empty selection. Catalogue evidence is text, optical evidence is two images, and topography is numeric text plus three images. All modalities therefore produce five images. Test memory requirements on the available GPU before running an experiment; compatibility with an earlier 15 GB setup is not guaranteed. Use a new RUN_ID and compare within the same representation protocol.

## Colab integration

Upload the complete new package and extension directory, preserving the existing repository. Adjust paths to the uploaded locations:

```python
import sys
from pathlib import Path

REPO = Path("/content/autonomous-modality-selection")
sys.path.insert(0, str(REPO / "extensions/evidence_views_v1/src"))
sys.path.insert(0, str(REPO / "src"))
from ams_evidence_views.adapter import build_content

TRIAL_PACKAGE = Path("/content/evidence-views-v1/crater-16604")
trial_content = build_content(TRIAL_PACKAGE, question, selected)
trial_messages = [{"role": "user", "content": trial_content}]
# Pass this to your multimodal inference function, preserving every image block.
# Keep the existing generate_reply, select_inputs and answer_question unchanged.
```

Preserve the five-image routing: a legacy PREVIEWS dictionary must not collapse the package or omit context/profile images. The adapter supplies numeric text and images; it does not give the model tools to operate directly on GeoTIFF or CSV files. This builder leaves selection budgets, modality costs and experimental conditions to the calling runner. The selected-modality allowlist controls content routing. Review notes and selector rationales stay outside the answer prompt.

The current AGENT_ITERATIVE runner uses this adapter; see `docs/colab_iterative_notebook.md`.

## Tests and rollback boundaries

```powershell
.venv/Scripts/python.exe -m pytest extensions/evidence_views_v1/tests
.venv/Scripts/python.exe -m ruff check extensions/evidence_views_v1
.venv/Scripts/python.exe -m ruff format --check extensions/evidence_views_v1
```

Current root-level pytest configuration includes extension tests. If the default temporary directory is inaccessible, choose a new `--basetemp` directory under `tmp/` and a separate cache directory.

To stop using these representations, stop the relevant experiment process or Colab cells and retain the original evidence packages. Newly generated representation-trial directories can be removed after inspection. The current iterative runner and integrated tests depend on the extension, so removing its code requires also disabling those new entry points and their tests. Historical evidence and baseline entry points remain available; no raw-data deletion or redownload is required.

See `VERIFICATION.md` for the original pre-integration checks. Those historical results are distinct from current repository verification.
