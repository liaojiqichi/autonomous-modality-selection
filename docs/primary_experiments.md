# Active experiment protocol: richness-ap-dual-model-2.0

The sole active configuration is configs/experiment_protocol.json, bound to the final
PDF checksum. Earlier preparations remain historical and must not be pooled.

## Design

- Models: Qwen/Qwen3-VL-8B-Instruct, google/gemma-4-E4B-it (provisional).
- Four conditions: NO_DATA, ALL_AVAILABLE, RANDOM, AGENT.
- Costs: catalog 1, optical 2, topography 2; maximum two selected modalities.
- Primary budget 4; sensitivity budget 3. All-available costs 5 and ignores selection caps.
- Five uniform random draws WITH replacement per scenario; both models share choices.
- An implementation master seed plus scenario, budget and draw index derives a stable
  integer seed. Duplicate subsets remain legitimate draws. This is an implementation
  detail, not an additional thesis requirement.
- Greedy answers; freeze model revisions, quantization, thinking, image processing and
  output caps before formal tests. Fixed seeds alone do not guarantee hardware determinism.
- 30 targets x 4 questions x 8 records x 2 models = 1,920 primary answer-attempt records.
  Selector and evaluator calls are additional. Five draws are not five independent targets.

## Local execution

Run the command in the root README. Packages are checksum-verified and referenced,
never copied. Use a fresh output directory. AGENT remains pending, not rule-substituted.
Preparation stores model IDs, draw IDs, shared seeds, evidence hashes, proposal and
protocol hashes, and a generator whitelist that excludes unselected metadata/rationales.

The current pool contains seven previously inspected targets. It is development material;
selecting the final six requires a reviewed split. Held-out execution is blocked until
an independent 30-target split and input compatibility have been reviewed.
Pass `--split held_out --split-file <reviewed.json>` to use the validated TargetSplit
schema. It requires 6 development IDs, 30 disjoint held-out IDs, reviewer identity,
all previously inspected IDs and approval. The known 12-target historical pilot is
checked independently. Later external/Colab inspection history must also be included.
The split hash is saved. A missing target package is an error, not a skipped scenario.
Do not silently manufacture or repeat craters to reach the sample target.

## Generation and evaluation gates

1. Reuse evidence_views_v1 packages; preserve all local/context/profile images and numeric text.
2. Run a small Colab GPU compatibility pilot for EACH checkpoint; do not assume 15 GB is enough.
3. Pin both model configurations and equivalent prompt content; verify selection JSON,
   empty no-data input, ALL_AVAILABLE hard input limits, failures and truncation logging.
4. Freeze target split and questions before new held-out answers.
5. Annotate A/P using the source-span rubric; retain evaluator identities and raw outputs.
6. Draw human review cases by model/condition/question family before inspecting richness;
   use one RANDOM draw per sampled scenario. Diagnostic examples are a separate sample.
7. Average RANDOM draws within scenario; compare agent, then aggregate equally across craters.
   Do not treat questions/draws as independent crater replicates.

Local preparation does not run a model, perform annotation, or create scientific results.
The active source checkout has no connected GPU session. These gates must be reported,
not bypassed with fabricated answers. Schedule remains advisory.
