# Replace Qwen RANDOM with exact-two draws

Open `notebooks/qwen_heldout_random_exact_two_resume.ipynb` in Colab and run it
from top to bottom on the original GPU type (the inspected run used Tesla T4).
The notebook visits all 30 held-out targets automatically. No batch selection
or prepare inference is needed. Only 600 RANDOM answers are generated.

## Paths and continuation

- Active run: `/content/drive/MyDrive/ams-formal-results/heldout-evidence-revision-v23-001`.
- Retired originals: `/content/drive/MyDrive/ams-formal-results-retired/heldout-evidence-revision-v23-001`.
- The dataset folder or ZIP is configured in the first code cell.
- Keep the run label and paths unchanged when continuing after interruption.
- In a new runtime, run all cells again. In the same initialized runtime, rerun
  the runner cell. Verified replacements are skipped; remaining failed attempts
  receive one new attempt per execution, with the earlier failure retained.
- Dependency installation may require one session restart. The model and
  processor use the original immutable checkpoint and pinned package versions.

## Sampling

The new draw is `random.Random(scenario_seed(42, case_question, 4, draw)).sample`
over the sorted four modality names, taking exactly two distinct names. There
are six equally probable pairs. Five draws are made per question with
replacement between draws. This is the same implementation as the inspected
Gemma exact-two run; all 600 recorded Gemma selections were checked offline.
The historical value 4 is retained solely as part of the shared seed derivation
and existing folder layout. Every pair is eligible.

## File handling

Before replacement, the notebook verifies the original target metadata, model
revision, generation function, environment, processor, prompts and input hashes.
It makes safety copies of NO_DATA, ALL_AVAILABLE and AGENT outside the active run
and checks that their bytes remain unchanged. It moves revision attempt files,
their started sidecars and target revision metadata outside the active folders.

A new successful RANDOM record replaces its original
`Qn__RANDOM__rNN.json` only after the original has been backed up and verified.
If the new generation fails or truncates, the old file remains and the failure
is recorded under the retired directory's `failed-new-attempts` folder.
That old RANDOM record is explicitly **pending replacement**, not an eligible
result under the new sampling design. Do not run concurrent writers on this run.

The original `run_metadata.json` continues to describe the preserved baselines.
The new `random_exact_two_metadata.json` describes the replacement RANDOM records;
their `run_sha256` points to that file. The run-level
`active-four-condition-index.json` lists each active file, status, metadata path
and hash, and marks pending replacements. It excludes revision records.
Readers must use this index instead of assuming one metadata file describes
every condition. Once complete, the active run has 960 baseline records:
120 NO_DATA, 120 ALL_AVAILABLE, 120 AGENT, and 600 new RANDOM.

## Verified historical implementation

The archive `qwen3-vl-8b-20261028T230001Z-1-001.zip` contains successful records for
all 30 targets and all four baseline conditions. Its initial AGENT selections
all contain two modalities. Its implementation was
`autonomous_modality_selection_answer_revision_formal.ipynb` at commit
`dd429496a0b4cd429818cc789a9a10a3df941805`, notebook SHA-256
`716eeb6ab274ca096143df22bc712b9f1bea871a07b92ea4cfbff631731bc325`.

The replacement notebook reuses that archived target adapter and generation
code. It embeds the replacement helper, so it can run without installing a newer
project revision or importing new modules into the pinned checkout. Model
inference has not been run locally; the tests use synthetic fixtures.
