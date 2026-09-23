# Historical isolated-extension verification

> English translation of the verification record at commit `3b91476`.
> This record describes the original isolated implementation, before integration
> with the iterative agent and root test suite. Counts and rollback statements
> below refer to that stage, not a new execution.

That stage added only the extension and trial outputs. Root configuration, existing modules, previous notebooks and extracted evidence remained unchanged.

## Generated packages

Complete batch:

`experiments/benchmarks/mercury-screened-v2-20260907/representation_trials/evidence-views-v1/batch-01/`

| Directory | Target |
| --- | --- |
| crater-16604 | Eminescu |
| crater-1851 | Giotto |
| crater-19610 | Scarlatti |
| crater-2179 | Thoreau |
| crater-4870 | Mofolo |
| crater-5031 | Nampeyo |
| crater-858 | Soseki |

Each case has eleven output files plus `manifest.json`. The earlier single-case smoke check at `evidence-views-v1/crater-16604/` was retained; subsequent work was advised to use batch-01. All source data came from existing packages, without downloading again.

## Recorded checks

- SHA-256 values of all 210 original files across seven cases were unchanged after batch generation.
- Schema validation, output sizes, hashes and PNG decoding passed for all seven new packages.
- New and original east-west CSVs matched in shape and elementwise distance/elevation values: rtol=0, absolute tolerance 0.001; column units km and m respectively.
- Full-modality routing contained five images. Single-modality routing excluded other modalities' images and numeric content.
- Five Eminescu images received visual inspection, without planetary-science expert certification.
- Original tests alone: 139 passed.
- Extension tests alone: 17 passed.
- Combined run: 156 passed, with 150 Rasterio/Affine deprecation warnings and no failures.
- `ruff check extensions/evidence_views_v1 src tests` and the equivalent format check passed.
- Repository-wide lint and format checks found a pre-existing import/format issue in `tmp/pdfs/proposal-20260914/check_proposal.py`. That file and root configuration were left unchanged at the time.
- At that stage, `git diff --stat` was empty because existing tracked files were unchanged. Existing output/ and tmp/ directories were untracked.

## Work not performed and limitations

That verification included no LLM calls, new answer experiments, scientific annotation, Colab memory validation or GitHub commit/push. Five-image input may require more GPU memory than the old two-preview input. A fresh notebook cell and RUN_ID were recommended for resource tests. Existing functions, budgets and costs were unchanged.

## Original rollback boundary

At the isolated stage, new code, tests, documentation, temporary checks and outputs lived under `extensions/evidence_views_v1/` and `representation_trials/evidence-views-v1/`. Removing those additions after stopping execution left original data intact.

The extension is now used by iterative-agent entry points and included in root tests. Consult the current README before removing it; the original isolation claim does not describe those later integrations.
