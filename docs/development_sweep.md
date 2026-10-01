# Exhaustive input-combination diagnostic (development only)

This opt-in diagnostic keeps the original experiment and notebook interfaces.
No downloads, model loading, selector changes or historical-result edits occur.

## Design

With ordinal costs catalogue=1, optical=2 and terrain=2, budget 4 and at most two
modalities permit six nonempty subsets: each singleton and each pair. Four
questions therefore require **24 answers**. Budget 3 has five subsets (20 answers).
Cost units are explicitly legacy ordinal units, not measured tokens.

By default the diagnostic adds NO_DATA and ALL_AVAILABLE references, giving
**32 answers** at budget 4. ALL_AVAILABLE is outside the feasible search. Empty
input is outside the original one-shot/RANDOM nonempty set, but can represent
AGENT_ITERATIVE's initial FINISH when no required modality exists. Report that
difference explicitly when comparing iterative choices. No selectors are rerun.

The original EN-003 archive covers 16 of the 24 nonempty question/subset cells.
Eight are absent: Q1 catalogue, terrain, catalogue+optical; Q2 catalogue,
catalogue+optical; Q3 catalogue, optical; Q4 terrain. Existing observations can be
compared descriptively. The new runner generates a fully pinned matrix in a new
directory; it deliberately does not pool eight new answers with old answers from
potentially different functions, settings or environments. Use existing data and
the already loaded model; only small result JSON files are added.

## Colab: setup without inference

Transfer the new module and example to the Colab checkout (or pull after you have
explicitly pushed them). No push is performed by this task. Preserve any local
notebook changes; the existing notebook need not be replaced. Restart imports if
an older development_sweep module has already been loaded.

Run the existing notebook's configuration, generation and answer-routing cells.
The full five-condition loop is unnecessary. Do not reload a working model.
Verify the GPU preflight as usual and check the desired answer token cap and
repetition penalty in the actual functions. All combinations use the same current
answer function; the runner does not change those settings. EN-003's archived
answer function specified 1.2, despite a user description of 1.1; this discrepancy
must be resolved before asserting a matched historical comparison.

```python
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location(
    "colab_development_sweep",
    Path(PROJECT) / "examples" / "colab_development_sweep.py",
)
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)

# Reads/hashes existing evidence and prints the planned number of calls.
# Does not generate any answers.
sweep_plan = sweep.prepare_from_notebook(globals(), include_references=True)
```

## Colab: start the experiment explicitly

```python
SWEEP_OUTPUT = Path("/content/experiment-results/emin-combinations-001")
attempts = sweep.run_from_notebook(globals(), SWEEP_OUTPUT, include_references=True)
```

No extra model instance is created. Repeated execution with identical configuration
skips every existing record, including errors and interruptions. It never repairs
JSON, retries inference or replaces failed historical attempts. Change the output
directory after changing any model, function, setting, evidence or requirement.
Keep model/configuration globals unchanged while running. A started record denotes
an interrupted attempt and must not be treated as successful or scored zero.

```python
from collections import Counter

print(Counter(record.status for record in attempts))

import shutil
from google.colab import files

archive = shutil.make_archive(str(SWEEP_OUTPUT) + "_results", "zip", SWEEP_OUTPUT)
files.download(archive)
```

## Evaluation

Annotate all completed cells with the same versioned A/P rule and independent
quality dimensions. Do not select the richest draw from RANDOM or count identical
answers as independent craters. The exported text is `generation.text`; keep
`question_id`, `combination.selected`, `messages` and source hashes for auditing.

For each question, map the recorded AGENT and AGENT_ITERATIVE choices onto the
fresh matrix, labeling these as **frozen historical selections evaluated with the
fresh answer pipeline**. This measures how those choices compare within the new
matrix; it is not a fresh end-to-end agent run. Re-run selectors separately under
a pinned new protocol if fresh end-to-end performance is needed.

Report the observed maximum A and maximum P separately, which may belong to
different combinations; report each agent's dimension-specific gaps. Also list
combinations that weakly exceed both A and P and strictly exceed one (richness
Pareto dominance), with their quality judgments alongside. Never collapse A/P into
an undeclared total or call the observed maximum a proven optimum.

If some cells fail or truncate, label the matrix incomplete; do not insert zeros
or infer an exhaustive ranking. Quality concerns remain visible even when an
alternative has more ideas. A complete one-crater matrix diagnoses this development
case only; it does not establish general selector effectiveness.
