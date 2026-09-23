"""Opt-in Colab entry point; importing this file performs no inference or downloads."""

from pathlib import Path

from autonomous_modality.iterative import (
    Generate,
    IterativeAnswer,
    IterativePolicy,
    run_iterative_answer,
    run_iterative_selection,
    save_iterative_answer,
)
from autonomous_modality.iterative_evidence import evidence_view_loader
from autonomous_modality.models import InputSelectionRequest


def run_scenario(
    request: InputSelectionRequest,
    policy: IterativePolicy,
    generate: Generate,
    *,
    package_root: Path,
    case_id: int,
    model_id: str,
    shared_answer_prompt: str,
    answer_max_new_tokens: int,
    destination: Path,
) -> IterativeAnswer:
    """Run only the new group on an existing package with the loaded Colab model.

    Use the same answer prompt, representation package, decoding and cost table
    as the controls and one-shot ablation. Call only after verifying model setup.
    """
    if destination.exists() or "raw" in {p.lower() for p in destination.resolve().parts}:
        raise ValueError("choose a fresh result path outside raw data")
    loader = evidence_view_loader(package_root, expected_case_id=case_id)
    selection = run_iterative_selection(
        request, policy, generate, loader, model_id=model_id, execution_kind="model"
    )
    result = run_iterative_answer(
        selection, shared_answer_prompt, generate, max_new_tokens=answer_max_new_tokens
    )
    save_iterative_answer(result, destination)
    return result
