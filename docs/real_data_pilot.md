# Real-data preparation pilot

Pipeline version: `mercury-real-pilot-1.0`. This experiment checks acquisition,
data preparation, and deterministic selection. It does not call an LLM, generate
scientific solutions, or measure expert-annotated solution richness.

## Acquired products and scope

The first run uses the following public products. Downloads go to a new directory
under `data/acquired/`, leaving `data/raw/` untouched. Source files are read-only
inputs for the preparation adapter. Complete files have SHA-256 receipts;
rerunning acquisition checks existing files instead of overwriting them. Partial
downloads are retained and never accepted as complete sources.

| Source | Version and purpose | Access |
| --- | --- | --- |
| Herrick crater catalogue | 2011, Mariner 10/MESSENGER flybys; CSV and author README | [Author's public page](https://sites.google.com/alaska.edu/robertherrick/resources/mercury-global-crater-database) |
| MDIS LOI mosaic | MESS-H-MDIS-5-RDR-LOI-V1.0; 166 m grid, 8-bit display stretch | [USGS product page](https://astrogeology.usgs.gov/search/map/mercury_messenger_mdis_basemap_loi_global_mosaic_166m) |
| Global DEM | USGS 665 m grid, version 2; numeric heights | [USGS product page](https://astrogeology.usgs.gov/search/map/mercury_messenger_global_dem_665m) |

The [2018 catalogue attachment](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2017JE005516)
returned a publisher HTTP 403 challenge during acquisition. The older author-hosted
catalogue is an explicitly identified substitute, not relabelled as the 2018 data.
Historical morphology codes are retained verbatim, including unknown values.
Their scientific reliability and coordinate alignment require review.

Literature is contextual documentation for this pilot, not a fourth selected
scientific asset. No simulation data have been obtained. Optical imagery and the
stereo-derived DEM share MDIS ancestry and are not independent measurements.

## Preparation

1. Parse all catalogue rows with strict Pydantic fields. Reject invalid coordinates,
   nonpositive/nonfinite diameters, unexpected columns, and duplicate IDs.
2. Select named craters with diameters 50-150 km, absolute latitude below 45 degrees,
   and absolute east longitude between 15 and 150 degrees. This excludes polar
   geometry and both source mosaics' longitude seams. Sort by diameter then ID,
   and select 12 evenly spaced ranks. This is a convenience sample for engineering
   inspection, not a random or globally representative sample.
3. Read source CRS, affine transform, nodata, and scale/offset from each TIFF.
   Reproject bounded windows to a Mercury azimuthal-equidistant projection centred
   at each catalogue coordinate, using reference radius 2,439,400 m.
4. Prepare two image crops (width 2D and 5D) and one DEM crop (width 2D). Use
   bilinear resampling at each source's nominal grid spacing. Pixel size is not
   instrument resolving power or vertical accuracy. Reject windows crossing source
   boundaries; the pilot does not implement longitude wrapping.
5. Mask DEM nodata before applying the source scale and offset. The downloaded
   DEM uses scale 0.5. Write derived DEMs as float32 metres, scale 1. Preserve LOI
   display DN for visual inspection rather than claiming calibrated reflectance.
6. Save numeric GeoTIFFs, labelled PNG previews, a central east-west elevation
   profile as CSV, and a combined review image. DEM summary ranges describe the
   whole crop; they are not crater depth measurements. An even-row profile averages
   the two centre rows and preserves missing values.
7. Use a minimum valid-pixel fraction of 0.95 as a preparation gate. This is an
   explicit experimental threshold, not a scientific quality certification.
   Failed cases remain in the report and are not silently replaced. Matching
   projections does not remove source registration error.

The pipeline records each source checksum, consumed window, source scale/offset,
destination CRS, resampling method, derived checksum, coverage, and units. It
does not automatically recenter historical catalogue positions, infer missing
morphology labels, or assign a scientific quality score.

## Selection experiment

For each prepared case, run four question types under four conditions: all three
modalities with budget 5, budget 3, topography excluded, and imagery excluded.
Costs are fixed experimental input units: catalogue 1, imagery 2, topography 2.
They are not measured latency, memory cost, or token estimates.

Pilot 1.1 / run schema 1.1 records exactly one result or error per trial. A failed
coverage gate disables the affected modality, rather than silently removing the
whole crater from the trial matrix. Infeasible selections are retained as failed
trials and do not interrupt other selections. Raster preparation errors still
stop preparation and need diagnosis; this is not a resumable batch runner.
Case records are saved before selection. Historical 1.0 runs remain readable and
are not rewritten or retroactively labelled with the new rules.

Source loading resolves filenames within the supplied source directory, verifies
pinned source identities, sizes and SHA-256 checksums, and rejects duplicate
receipts. Moving the source directory no longer requires editing old receipts.
This portability fix covers source loading, not all derived-product paths in
historical run files. Cropping supports single-band, north-up, square-pixel
Mercury grids projected in metres; other grids are rejected explicitly.

The 2D and 5D image crops represent one optical modality. Numeric DEM, DEM display,
and elevation profile represent one topography modality. Each request still has
one asset per scientific modality, consistent with schema 2.0.

Selection uses validated asset availability plus the existing hand-authored
capability descriptions and baseline scores. It does not inspect image content.
Consequently, identical choices across craters with the same capabilities and
coverage are expected. This experiment verifies the data-to-decision pipeline;
it cannot establish which modality set generates the richest scientific answer.

## Reproduce

Install optional preparation dependencies in the project environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,pilot]"
```

Acquisition requires network access and approximately 4.8 GB of source storage:

```powershell
.\.venv\Scripts\python.exe -m autonomous_modality.acquisition --directory data/acquired/mercury-pilot-20260905
```

Preparation and selection run offline. Supply a new output directory on each run:

```powershell
$env:MPLCONFIGDIR = "$PWD/.cache/matplotlib"
.\.venv\Scripts\python.exe -m autonomous_modality.pilot --sources data/acquired/mercury-pilot-20260905 --output experiments/runs/mercury-real-pilot-20260905 --sample-count 12
```

Open `report.html` in that output directory. `run.json` retains source receipts,
configuration, code/template hashes, library versions, selected targets, derived
products, and every selection request/result. Per-crater `case.json` and
`catalogue.json` provide smaller inputs for inspection. All JSON records use
strict Pydantic contracts; no generated solution or expert score is invented.

Unit tests use small explicitly synthetic files and mocked HTTP responses. They
need no network or real planetary files. Optional raster tests skip when the
pilot dependencies are absent; full pilot verification installs those dependencies.
