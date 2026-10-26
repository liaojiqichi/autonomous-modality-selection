# Unified four-modality descriptions

Version: `mercury-four-modality-descriptions-2.0`.

`src/autonomous_modality/modality_descriptions.py` is the maintained source. Each
modality has Contents, Coverage, Supported analyses and Interpretation limits.
Descriptions concern the existing compact packages. Costs, scientific data, answer
policy, questions and model settings are unchanged. Spectral declarations specify
the actual four regions and eight bands. Historical manifests and frozen inventories
retain their original descriptions.

## Public answer-revision notebook

Open the updated `notebooks/autonomous_modality_selection_answer_revision_formal.ipynb`
after pulling the repository. The settings cell enables:

```python
REVISION_ASSET_DESCRIPTION_VERSION = "mercury-four-modality-descriptions-2.0"
```

This amendment applies to the reviewer only. The initial one-shot AGENT and other
baseline conditions keep their frozen descriptions, allowing attribution to the
reviewer-side change. The public notebook still uses its existing reviewer action
schema; this update does not import private selected-set reviewer code.

Use a new revision run label (the new default is
`heldout-answer-revision-descriptions-v2-001`). The revision metadata records the
version, the actual amended assets and the description-module hash. The execution
fingerprint also records the version and module hash. Setting the variable to `None`
retains legacy descriptions; that also requires a separate run label.

## Existing Colab notebooks using saved initial answers

Pull before importing the project:

```python
import subprocess
from pathlib import Path

PROJECT = Path("/content/autonomous-modality-selection")
subprocess.run(["git", "-C", str(PROJECT), "pull", "--ff-only"], check=True)
```

Add the following to the settings cell, before computing fingerprints or entering
the target loop:

```python
REVISION_ASSET_DESCRIPTION_VERSION = "mercury-four-modality-descriptions-2.0"
REVISION_RUN_LABEL = "gemma-answer-revision-selected-v3-descriptions-v2-001"
REVISION_RESULTS_ROOT = RESULTS_ROOT / REVISION_RUN_LABEL
```

Record the change in the existing fingerprint before creating execution locks:

```python
from autonomous_modality import modality_descriptions

REVISION_FINGERPRINT["asset_description_version"] = REVISION_ASSET_DESCRIPTION_VERSION
REVISION_FINGERPRINT["asset_description_sha256"] = hashlib.sha256(
    Path(modality_descriptions.__file__).read_bytes()
).hexdigest()
```

Keep the existing reviewer extension, target list and baseline source. Do not replace
`ASSETS` or `CONFIG["assets"]` in this saved-answer workflow: they validate the initial
experiment. The updated `revision_colab.build_revision_request` applies the amendment
to a separate copy only when constructing reviewer inputs. It also records that copy
in `reviewer_asset_amendment` in each target's revision metadata. Unknown version
strings raise an error. Never bypass baseline checks to adopt descriptions.

If these modules were imported before `git pull`, stop any running target loop and
reload `modality_descriptions` followed by `revision_colab`. Then rerun the notebook's
reviewer-extension cell: reloading `revision_colab` resets any custom reviewer function
installed in memory. Rebind `run_target_revisions` from the reloaded module, rerun the
fingerprint/extension setup and use a new revision label. Model weights need not be
reloaded for these source-only changes. If the settings cell resets `DATASET_ROOT`,
rerun dataset location/context setup before the target loop.

## New runs that update every selector

For an ordinary development run, insert this after assembling all four `ASSETS`
entries and their inventories, but before constructing `CONFIG`:

```python
from autonomous_modality.modality_descriptions import (
    ASSET_DESCRIPTION_VERSION,
    describe_assets,
)

ASSETS = describe_assets(ASSETS)
```

Add these entries to `CONFIG`:

```python
"asset_description_version": ASSET_DESCRIPTION_VERSION,
"inventory_version": ASSET_DESCRIPTION_VERSION,
"assets": ASSETS,
```

Use a fresh `RUN_LABEL`. This updates both one-shot and iterative selectors that read
`ASSETS`. For a multi-target notebook, place the change inside the per-target setup
source before `CONFIG`; otherwise the next target will reconstruct the old assets.
Do not enable an older optical-description override later in that setup. Historical
ablation notebooks retain their controlled variants and do not automatically adopt
this intervention. The generic multispectral adapter can describe other shapes;
only this compact-package amendment declares exactly four regions and eight bands.

For inspection before inference:

```python
from autonomous_modality.revision_colab import reviewer_assets

print(reviewer_assets(globals())["OPTICAL_IMAGE"]["description"])
```

For a new all-selector development run, print `ASSETS` instead. After execution,
check the actual selector/reviewer messages and saved metadata, not just the version
label. This update adds no model inference, external search, automatic retries or
scientific data downloads.
