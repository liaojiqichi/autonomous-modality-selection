# Active research design — final PDF alignment

Source: user-supplied Autonomous_Modality_Proposal.pdf, 18 September 2026.
SHA-256: 62168e04286f7f2937524dba458e1e38fd24ce486f43b73934f8d7e575989360.

Title: An AI Agent for Autonomous Input Modality Selection in Scientific Problem
Solving: A Case Study of Planetary Crater Questions.

The agent-improves-richness claim is a hypothesis, not a guaranteed result.
Primary outcomes are A (distinct executable analyses) and P (distinct explanations).
The PDF's RQ1 still mentions cross-modal insights; section 3.3 and the user's explicit
correction take precedence. Cross-modal correspondence is a QUESTION FAMILY, not a score.

Core modalities: catalog, optical imagery, topography. Representations do not create
additional scientific modalities. Inputs reuse existing catalog records, local/context
images and numerical terrain/profile representations. Optical and DEM share MDIS
ancestry and are not independent sensor confirmations.

Two model families: Qwen3-VL-8B-Instruct and provisional google/gemma-4-E4B-it.
Each performs selection and generation in its own four-condition experiment.
Primary comparisons are within model, not a causal comparison of selectors alone.
All-data is an unbudgeted reference. Random and agent share feasible options.

Target: six development and thirty held-out craters, four questions each.
Development/inspected targets must not be relabeled as independent held-out cases.
Current data availability does not establish the target sample size.

All answers receive LLM annotations; where feasible use two separate evaluators.
A stratified human audit has 64 answers (2 models x 4 conditions x 4 families x 2),
plus up to 16 separately reported diagnostic examples. This is not full human ground truth.
Report scenario-level agent-minus-mean-random differences, then equal-weight crater means.
Keep quality, failures, truncation, length, frequencies and costs separate.

The timetable is reference only. No recurring monitoring/reminder has been created.
See primary_experiments.md for executable preparation and outstanding inference gates.
