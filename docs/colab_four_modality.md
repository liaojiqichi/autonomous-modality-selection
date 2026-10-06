# Four-modality development experiment in Colab

Open `notebooks/autonomous_modality_selection_four_modality.ipynb` in Colab.
Use a fresh GPU runtime and execute the cells in order. The original iterative
notebook remains available for historical three-modality runs.

The download cell fetches the pinned public GitHub Release archive (292 MB),
checks its SHA-256, validates archive paths, and verifies the released files.
No global source tiles need to be downloaded again. Upload and local/Drive ZIP
options are included for networks that cannot download release assets.

Available development targets are Nampeyo (5031), Thoreau (2179), Soseki (858),
Mofolo (4870), Eminescu (16604), Scarlatti (19610), and Giotto (1851).
Set `TARGET_ID` in the configuration cell; Eminescu is the default. Reuse the
loaded model to run another target by rerunning from configuration onward.
Use a fresh `RUN_LABEL` after changing prompts, parameters or source code.

## Inputs and protocol

The modalities are CRATER_CATALOG, OPTICAL_IMAGE, TOPOGRAPHY and
MULTISPECTRAL_IMAGE. The multispectral input is a validated numeric summary of
eight real MDIS wavelength bands and spatial regions. It is not a new optical
preview or a mineral identification product. The full numerical cube and
source provenance are in the downloadable package. Cross-modality QA figures
are excluded from model inputs to avoid leaking other modalities.

Core images are resized to 448 pixels on their longest edge in a separate run
folder. Original data remain unchanged. The multispectral summary is identical
for selector observations and final answers. Every selected input is checksummed.

Costs are ordinal experimental units: catalogue 1; each other modality 2.
The default budget is 4 with at most two cumulative acquisitions. ALL_AVAILABLE
uses all four modalities (cost 7) as an unconstrained reference. Budget 3 is a
separate sensitivity setting. These settings are a development extension.

Each target produces 36 attempts: four questions, each with NO_DATA,
ALL_AVAILABLE, five RANDOM draws, one-shot AGENT and AGENT_ITERATIVE.
Seven targets therefore produce 252 attempts per model. Search is disabled.
The existing Qwen3-VL-8B loading settings are preserved: four-bit loading,
512-token selectors, 1,024-token answers, deterministic decoding and answer
repetition penalty 1.2. The notebook does not claim Gemma runtime verification.

The all-input preflight checks the actual processor and GPU before experiments.
Four-modality inputs can consume more memory; fitting on a particular Colab GPU
is verified by this preflight, not guaranteed by local unit tests. Failures and
truncations remain recorded; existing attempts are never silently replaced.
Download the results ZIP after each target before ending a Colab session.

All seven targets have already been inspected and remain development data.
Technical correspondence checks and AI-assisted visual review are not an expert
geological assessment or subpixel registration validation. Scarlatti has a small
documented context coverage gap; consult the release manifests before analysis.
