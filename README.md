# Autonomous Input Modality Selection

New opt-in development experiment: [bounded iterative agent](docs/iterative_agent.md).
`AGENT_ITERATIVE` acquires real existing evidence at most twice, with one feedback
decision and cumulative access costs. Historical `AGENT` remains the one-shot
ablation. The default preparation interface and existing data are preserved.

Ready-to-upload Colab notebook:
[autonomous_modality_selection_iterative.ipynb](notebooks/autonomous_modality_selection_iterative.ipynb).
It adapts the user's working AP notebook, retains its receipt-based inputs and
generation interface, and runs 36 development attempts per crater/model. See the
[notebook instructions](docs/colab_iterative_notebook.md) before running.

Active design: [experiment protocol](docs/primary_experiments.md).
Research summary: [proposal alignment](docs/research_proposal.md).
Annotation: [A/P rubric](docs/richness_annotation.md).

The experiment tests whether input selection improves two separately reported outcomes:
analytical approaches (A) and explanatory perspectives (P). There is no C score,
cross-modal weighting or composite richness score. Scientific validity and evidence
fidelity are independent checks. Proposed executable analyses may count.

## Setup and verification

Python 3.12+. Install with `python -m pip install -e ".[dev,pilot]"`.

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Tests include the reusable evidence-view extension and require no real data or network.
On Windows with inaccessible default temporary directories, supply a NEW
`--basetemp tmp/checks-<unique-id>` and `-o cache_dir=tmp/cache-<unique-id>`.

## Prepare the current development pool

```powershell
python -m autonomous_modality.experiments --benchmark experiments/benchmarks/mercury-screened-v2-20260907 --output experiments/primary/ap-development-new --budget 4 --seed 42
```

This verifies existing packages, references their files without copying large data,
and prepares two models x four questions x eight condition/draw records per target.
NO_DATA, ALL_AVAILABLE and AGENT each have one record; RANDOM has five draws.
Agent records remain pending until actual inference. Preparation is NOT an answer experiment.
Budget 3 is a separate sensitivity preparation; output paths must be new.

The seven previously screened packages are a development POOL, not seven held-out
targets or the final six-target development split. Formal evaluation requires a
reviewed split with 30 independent held-out craters; this gate is deliberately closed.

## Code responsibilities

- `models.py`, `evaluation.py`: A/P annotations with spans, duplicate groups and quality.
- `protocol.py`, `configs/experiment_protocol.json`: final-proposal design constants.
- `experiments.py`: checksummed, paired dual-model preparation.
- `iterative.py`, `iterative_evidence.py`, `iterative_colab.py`: bounded acquisition,
  read-only evidence packages and an opt-in bridge to the existing Colab generator.
- `examples/colab_iterative.py`: run only the new condition using an already loaded model.
- `benchmark.py`, `pilot.py`, `acquisition.py`: reusable read-only source validation,
  crop extraction and evidence packaging; older trial commands are auxiliary.
- `selection.py`, `ams-demo`: deterministic AUXILIARY baseline, never the AI agent.
- `extensions/evidence_views_v1/`: reusable numeric terrain, profiles and local/context views.
- `docs/colab_setup.md`: environment/data transfer; large rasters must not enter Git.

Historical experiments are retained as evidence of previous protocols, not migrated
or pooled with new A/P results. Old three-dimensional annotation payloads are rejected.
Old proposal PDFs in output/ are not active protocols. Data/raw and acquired data are read-only.
No credentials, automatic downloads, paid model calls or GitHub pushes are performed.
The schedule is a reference, not an automated reminder.
