"""Create a question-only protocol overlay without copying or changing evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import QuestionSet
from autonomous_modality.heldout import Cohort, write_new
from autonomous_modality.heldout_protocol import Design, FrozenProtocol, freeze_design

DEFAULT_QUESTIONS = Path("configs/mercury_selection_questions_v2.json")


def revise(base: Path, output: Path, questions_path: Path = DEFAULT_QUESTIONS) -> None:
    """Validate a frozen design and write a separate question-only revision."""
    if output.exists():
        raise FileExistsError(output)
    frozen = base / "frozen"
    protocol = FrozenProtocol.model_validate_json((frozen / "protocol.json").read_bytes())
    cohort = Cohort.model_validate_json((base / "cohort.json").read_bytes())
    old = QuestionSet.model_validate_json((frozen / "questions.json").read_bytes())
    design = Design.model_validate_json((frozen / "design.json").read_bytes())
    questions = QuestionSet.model_validate_json(questions_path.read_bytes())
    if protocol.cohort_sha256 != sha256_file(base / "cohort.json"):
        raise ValueError("BASE_COHORT_CHANGED")
    if protocol.question_sha256 != sha256_file(frozen / "questions.json"):
        raise ValueError("BASE_QUESTIONS_CHANGED")
    if freeze_design(cohort, old) != design:
        raise ValueError("BASE_DESIGN_CHANGED")
    if sha256_file(frozen / "design.json") != protocol.pinned_files["design.json"]:
        raise ValueError("BASE_DESIGN_HASH_CHANGED")
    if [q.question_id for q in questions.questions] != ["Q1", "Q2", "Q3", "Q4"]:
        raise ValueError("EXPECTED_Q1_TO_Q4")
    if questions.version != "mercury-selection-value-2.0-en.1":
        raise ValueError("EXPECTED_SHARED_QUESTION_VERSION")
    updated = freeze_design(cohort, questions)
    assert updated.human_review_slots == design.human_review_slots
    for before, after in zip(design.scenarios, updated.scenarios, strict=True):
        assert before.random_budget_3 == after.random_budget_3
        assert before.random_budget_4 == after.random_budget_4
    output.mkdir(parents=True)
    write_new(output / "questions.json", questions)
    write_new(output / "cohort.json", cohort)
    write_new(output / "design.json", updated)
    payload = protocol.model_dump(mode="json")
    payload.update(
        version="heldout-four-modality-ap-1.1",
        revision_authority="User approved shared revised questions on 2026-10-16.",
        question_sha256=sha256_file(output / "questions.json"),
        cohort_sha256=sha256_file(output / "cohort.json"),
        pinned_files={p.name: sha256_file(p) for p in sorted(output.iterdir())},
    )
    write_new(output / "protocol.json", FrozenProtocol.model_validate(payload))
    manifest = {
        "version": "question-only-revision-20261016",
        "base_release": base.name,
        "base_release_sha256": sha256_file(base / "release.json"),
        "base_protocol_sha256": sha256_file(frozen / "protocol.json"),
        "base_question_sha256": protocol.question_sha256,
        "files": {p.name: sha256_file(p) for p in sorted(output.iterdir())},
        "inherits": "Evidence, prompts, runtime settings and rubric from base release.",
        "changes": "Question text and answer requirements only; draws and review slots unchanged.",
        "runtime_approved": False,
        "model_inference_performed": False,
    }
    with (output / "revision.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)


def main() -> None:
    """Build a small portable overlay beside an immutable dataset release."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    args = parser.parse_args()
    revise(args.base, args.output, args.questions)


if __name__ == "__main__":
    main()
