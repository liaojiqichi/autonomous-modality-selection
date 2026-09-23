# Real-data pilot record: 5 September 2026

> English translation of the historical report at commit `3b91476`.
> Dates, findings and validation counts describe that pilot, not a new execution.

Run ID: `mercury-real-pilot-20260905`. This pilot prepared data and performed deterministic modality selection. It produced no LLM answers or expert answer scores.

## Acquired and processed data

- Source files totalled 4,778,972,401 bytes (approximately 4.78 GB), all with recorded SHA-256 checksums.
- Herrick's publicly available 2011 CSV contained 16,876 records, accompanied by the author's field descriptions.
- USGS global elevation DEM v2: 530,934,581 bytes.
- MDIS LOI global image mosaic v1: 4,247,471,083 bytes.
- Source files are under `data/acquired/mercury-pilot-20260905/`. Nothing was written to or changed under `data/raw/`.

The publisher's HTTP 403 verification page blocked the 2018 catalogue attachment. This pilot therefore used the 2011 catalogue explicitly. Its historical coordinates and morphology labels still require manual review.

## Sampling and preparation

The selection criteria were named targets, diameters of 50–150 km, absolute latitude below 45°, and absolute east longitude between 15° and 150°. This yielded 82 candidates. Twelve evenly spaced ranks were selected after sorting by diameter and catalogue ID. Targets were not resampled according to image quality or selection outcomes.

| Catalogue name | Catalogue ID | Historical catalogue diameter (km) |
| --- | --- | --- |
| Nampeyo | 5031 | 51.5 |
| Echegaray | 734 | 67.6 |
| Thoreau | 2179 | 75.0 |
| Bartok | 4512 | 83.2 |
| Soseki | 858 | 90.8 |
| Kenko | 6611 | 98.7 |
| Harunobu | 1695 | 105.8 |
| Mofolo | 4870 | 109.9 |
| Eminescu | 16604 | 119.4 |
| Scarlatti | 19610 | 126.3 |
| Holbein | 908 | 135.3 |
| Giotto | 1851 | 148.6 |

Each target received a 2D local image, 5D context image, 2D elevation raster, central east-west elevation profile, previews, catalogue JSON and asset descriptions. Here D denotes catalogue diameter. The 36 derived rasters totalled 480,928,554 bytes. Minimum valid-pixel coverage was approximately 99.654%; all twelve targets passed the predefined 95% preparation threshold. This threshold checks valid coverage only; it does not certify scientific accuracy or source registration.

Processing used a target-centred azimuthal equidistant projection with Mercury radius 2,439,400 m. Missing DEM pixels were masked before applying the TIFF scale factor of 0.5; output elevations are in metres. Optical values retain the source display stretch and are not claimed to be calibrated reflectance.

Checksums of source files and all 36 derived rasters were verified. Recorded code and template checksums matched the files at completion.

## 192 modality selections

Each target used four question types and four experimental conditions: 12 × 4 × 4 = 192 attempts. Manually assigned ordinal costs were catalogue 1, imagery 2 and topography 2, without a measured time or token interpretation.

| Condition | Result | Count |
| --- | --- | --- |
| Budget 5, all three modalities available | Imagery, catalogue and topography; order varies by question type | 48 |
| Budget 3 | Topography + catalogue | 36 |
| Budget 3 | Imagery + catalogue | 12 |
| Topography excluded | Imagery + catalogue | 48 |
| Imagery excluded | Topography + catalogue | 48 |

Every selection satisfied its constraints. No feasibility fallback was triggered; offline boundary tests cover that behaviour. Identical question types and conditions produced identical choices across craters because they passed the same availability checks and used the same manually specified capabilities and fixed scores. This confirms pipeline consistency, without establishing which combinations produce better scientific answers.

No answers were generated and no answer-richness values were computed or invented. Literature provided methodological context rather than a fourth selectable asset. Simulation outputs were unavailable.

## Inspection and review

- [Full illustrated report](../experiments/runs/mercury-real-pilot-20260905/report.html)
- [Inputs, outputs and provenance](../experiments/runs/mercury-real-pilot-20260905/run.json)
- [Reproduction and processing limits](real_data_pilot.md)

The next step at the time was manual review of catalogue-centre alignment with the visible crater and whether the DEM profile crossed the intended landform. Subsequent answer experiments would require a fixed model and generation settings, with independent expert richness assessment. See the current experiment protocol for the superseding evaluation design.
