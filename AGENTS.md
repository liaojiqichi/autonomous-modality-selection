# Project instructions

This repository implements a Master's thesis prototype for autonomous
scientific input-data-modality selection for Mercury crater questions.

## Scope

- The system selects scientific input data modalities from a closed, versioned taxonomy.
- The target outcome is solution richness: analytical approaches, explanatory
  perspectives (A/P only; no cross-modal insight score).
- Scientific modality and model representation must remain distinct concepts.
- The system models crater questions, available data assets, and resource constraints.
- The primary experiment conditions are no data, all available modalities,
  random selection, and AI agent selection. Rules and fixed pairs are auxiliary.
- Richness is measured separately from scientific validity and evidence fidelity.
  Proposed executable analyses may contribute without having been performed.
- Caloris quantitative inversion is out of scope. Preserve historical data and runs.
- Local preparation is offline; real model inference runs explicitly in Colab.
  Never label mocks, pending selections or preparations as model results.
- Reuse existing real evidence packages read-only; unit tests require no real data.
- Follow the final 18 September proposal: Qwen3-VL and Gemma 4, four conditions,
  five shared random draws with replacement, primary budget 4, sensitivity budget 3,
  at most two selected modalities. Historical inspected targets are not held-out.
- Schedule is reference only; flag delays only when they seriously threaten completion.
- Metadata-only fixtures may be used in tests, but must never be represented as
  downloaded or observed scientific data.

## Engineering rules

### Iterative development extension

- AGENT_ITERATIVE is the new feedback condition; AGENT retains historical one-shot
  semantics as an auxiliary ablation. Keep the original CLI default compatible.
- Acquire at most two existing modality packages, one per request, with one
  observation-informed revision. Log explicit model FINISH separately from system stops.
- Count all accessed evidence cumulatively. No replacement/refunds or hidden retries.
- Return verified real evidence through the existing evidence-view adapter; preserve
  raw/derived packages read-only. Selector rationales must not enter the answer context.
- Declare cost units explicitly. Historical 1/2/2 costs are ordinal, never measured
  tokens. Token budgets require externally measured/frozen processor-specific costs.
- This extension is a development experiment, not a rewritten signed proposal.
- Keep acquisition traces and tests separate from real model results and historical runs.

### General rules

- Target Python 3.12 or later.
- Use the `src` package layout.
- Add type annotations to all public functions and methods.
- Represent external inputs and persisted outputs with strict Pydantic models.
- Keep deterministic validation and scientific rules outside prompts.
- Every new behavior requires tests, including invalid-input cases.
- Do not require network access or real planetary data in unit tests.
- Preserve reproducibility: version schemas, prompts, configurations, and runs.
- Never commit API keys, credentials, raw confidential data, or `.env` files.
- Do not modify files under `data/raw/`; adapters must treat raw data as read-only.

## Verification

Before considering a change complete, run:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

If the required Python version or dependencies are unavailable, report that
clearly rather than claiming verification succeeded.
