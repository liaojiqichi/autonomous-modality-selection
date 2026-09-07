# Colab: private code repository, independent data download

The Git repository contains code, configurations, documentation and offline tests.
Scientific data, generated evidence packages, run outputs and local environments
are excluded. Keep the repository private. Never put a token in a clone URL,
notebook cell, output, or committed file.

## Code transfer

Create an empty private GitHub repository and push this code. In Colab, authenticate
using a temporary credential helper or an interactive GitHub CLI device login;
grant only the repository access needed. Clone the repository into /content/ams.
Do not copy the Windows virtual environment. Do not store Git credentials in Drive.
Verify that the cloned commit matches the intended local commit.

```python
import sys

assert sys.version_info >= (3, 12), sys.version
```

```python
%cd /content/ams
%pip install -e ".[dev,pilot]"
```

```python
!python -m ruff check .
!python -m ruff format --check .
!python -m pytest
```

## Download on Colab

Use a CPU runtime for data preparation; GPU time is unnecessary here. Reserve
at least 10 GB free disk for approximately 4.8 GB of sources plus derived files
and temporary downloads. Source URLs and exact byte sizes are pinned in
src/autonomous_modality/acquisition.py. Downloads record hashes and provenance;
an inaccessible or changed source is an error, not a reason to fabricate data.

```python
!python -m autonomous_modality.acquisition --directory /content/mercury-sources
```

This explicitly downloads the public catalogue, its README, the 665m DEM and
166m optical mosaic. It does not download the retired Caloris products or Qwen.
Persist completed source files and receipts in your own storage if needed;
/content is temporary. Existing verified downloads are reused by the downloader.

```python
!python -m autonomous_modality.pilot \
  --sources /content/mercury-sources \
  --output /content/mercury-pilot-001 \
  --sample-count 12
```

The pilot prepares crops, profiles and an inspection report. Its embedded rule
trials are auxiliary engineering checks, not the four primary thesis conditions.
Review the newly generated report before preparing primary experiments.

## Review boundary

Do not reuse configs/mercury_visual_reviews_v1.json as approval for a new run.
It is pinned to the original run hash, which changes with paths, timestamps and
environment. A new QA review manifest must explicitly refer to this Colab run.
Keep passing, held and rejected cases. Only then use benchmark packaging and
the four-condition runner described in primary_experiments.md. Do not bypass
hash checks or change a review's hash to pretend an old review covered new files.

No model inference is implemented by these commands. Agent conditions remain
pending until the Qwen adapter and answer runner are added. Save experiment
results separately from Git; do not commit acquired or derived scientific files.
