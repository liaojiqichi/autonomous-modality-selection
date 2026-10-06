# Multispectral development input

MULTISPECTRAL_IMAGE adds wavelength-dependent regional radiance-factor evidence.
Scientific modality and its numeric JSON representation are separate concepts.
Taxonomy: scientific-input-modalities-1.1; representation: multispectral-regions-1.0.
The initial adapter was followed by real acquisition on 6 October 2026.
The seven existing accepted benchmark targets now have official MDR v4 inputs
in experiments/benchmarks/mercury-four-modality-20261006. Its release.json and
visual_reviews.json record coverage, preservation checks and provisional visual
correspondence. Full PDS tiles are cached once in data/acquired/mdis-multispectral-v4-20261006.
Historical packages remain unchanged; model inference has not been performed.

## Preparation

For a new acquisition, run autonomous_modality.multispectral_acquisition with
--benchmark, --cache and explicit --allow-network. Prepare the downloaded data
offline with autonomous_modality.multispectral_dataset using --plan, --views and
a fresh --output directory. Make the evidence_views_v1 extension importable.
Record target-by-target visual observations, then finalize with
autonomous_modality.multispectral_release --dataset PATH --reviews REVIEW_JSON.
The release verifier also runs independently with --dataset PATH alone.

Install with pip install -e ".[multispectral,dev]".
Prepare a small calibrated, photometrically corrected MDIS WAC crop from the
[PDS MDR archive](https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=MESS-H-MDIS-5-RDR-MDR-V1.0).
Product calibration, georeferencing and region-mask preparation remain external
steps. RGB enhanced-color previews are not calibrated spectral bands.

The source NPZ contains float reflectance[band,y,x] in radiance factor I/F,
and one to eight boolean roi_<region_id>[y,x] masks. Convert nodata sentinels to
NaN beforehand. Supply SpectralMetadata with source, calibration reference,
spatial reference, case identifier, registration limitations, pixel resolution,
and ordered band identifiers/wavelengths in nm. Mark test data synthetic_fixture.
Metadata declarations require operator verification; validation does not prove
that a source was scientifically calibrated.

Use summarize_multispectral(source_path, metadata) to produce a strict JSON
package containing counts, means and population standard deviations by region
and band. Save package.model_dump_json(indent=2) to a new file outside data/raw.
Missing bands retain null values. Keep source and summary together.

Equivalent CLI (existing output files are never overwritten):

    python -m autonomous_modality.multispectral --source crop.npz --metadata metadata.json --output summary.json

## Colab integration

1. Load MultispectralPackage from the saved JSON. Create multispectral_asset
   with an explicit estimated_cost and append it exactly once to request.assets.
2. Create multispectral_loader(summary_path, expected_case_id=CASE_ID,
   source_path=crop_path). It pins the summary and verifies source hashes.
3. Wrap the existing evidence loader: route MULTISPECTRAL_IMAGE to the new loader;
   route other modalities to the unchanged existing loader. Pass this wrapper
   to the iterative selection runner.
4. Use autonomous_modality.iterative.answer_messages(trace, shared_answer_prompt)
   after a ready selection. This includes all acquired observations without
   selector rationales. The old notebook's three-modality answer builder does
   not automatically include multispectral evidence.
5. Update RANDOM, one-shot and ALL_AVAILABLE inventories consistently before
   running a four-modality comparison. NO_DATA still receives no evidence.

Use a fresh development run ID. Freeze the expanded candidate inventory,
representations, costs and random draws; record taxonomy, package versions and
file hashes. Ordinal costs must be labelled explicitly; token costs require
processor-specific measurement. At most two iterative acquisitions and cumulative
charging remain unchanged. Existing three-modality experiments remain unchanged.
The CLI demo exposes the new modality as unavailable. The rule baseline assigns
a provisional neutral score of 50, not an experimentally established benefit.

## Scientific boundaries

Regional spectral contrasts can support surface comparisons and illumination
alternatives. They alone do not establish mineral composition, absolute ages or
volcanic origins. MDIS grayscale and multispectral data share instrument ancestry.
Region masks are declared sampling regions, not confirmed geological units.
Only numeric summaries enter model context, not an executable spectral cube.
Scientific effectiveness still requires real-data preparation and Colab trials.
