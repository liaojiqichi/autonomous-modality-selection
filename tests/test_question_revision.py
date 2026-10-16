"""The active question set is shared, strict and preserves frozen sampling."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import QuestionSet
from autonomous_modality.heldout import write_new
from autonomous_modality.heldout_protocol import FrozenProtocol, freeze_design
from autonomous_modality.question_revision import DEFAULT_QUESTIONS, revise
from test_heldout_protocol import fixture_cohort


def test_shared_question_defaults() -> None:
    questions = QuestionSet.model_validate_json(DEFAULT_QUESTIONS.read_bytes())
    assert [q.question_id for q in questions.questions] == ["Q1", "Q2", "Q3", "Q4"]
    assert "surface material" in questions.questions[2].text
    for path in Path("notebooks").glob("autonomous_modality_selection*.ipynb"):
        if path.name.endswith(("four_modality.ipynb", "iterative.ipynb")):
            assert str(DEFAULT_QUESTIONS).replace("\\", "/") in path.read_text(encoding="utf-8")


def test_published_overlay_hashes_and_shared_questions() -> None:
    root = Path("configs/heldout_question_revision_20261016")
    manifest = json.loads((root / "revision.json").read_bytes())
    for name, expected in manifest["files"].items():
        assert sha256_file(root / name) == expected
    assert QuestionSet.model_validate_json((root / "questions.json").read_bytes()) == (
        QuestionSet.model_validate_json(DEFAULT_QUESTIONS.read_bytes())
    )
    protocol = FrozenProtocol.model_validate_json((root / "protocol.json").read_bytes())
    for name, expected in protocol.pinned_files.items():
        assert sha256_file(root / name) == expected
    assert protocol.question_sha256 == sha256_file(root / "questions.json")


@pytest.mark.parametrize("bad", ["version", "duplicate"])
def test_invalid_questions(bad: str) -> None:
    payload = json.loads(DEFAULT_QUESTIONS.read_bytes())
    if bad == "version":
        payload["version"] = "unversioned"
    else:
        payload["questions"][1]["question_id"] = "Q1"
    with pytest.raises(ValidationError):
        QuestionSet.model_validate(payload)


def test_revision_preserves_base_and_draws(tmp_path: Path) -> None:
    base = tmp_path / "base"
    frozen = base / "frozen"
    frozen.mkdir(parents=True)
    cohort = fixture_cohort()
    old = QuestionSet.model_validate_json(Path("configs/mercury_questions_v1.json").read_bytes())
    write_new(base / "cohort.json", cohort)
    write_new(frozen / "questions.json", old)
    write_new(frozen / "design.json", freeze_design(cohort, old))
    protocol = FrozenProtocol(
        version="heldout-four-modality-ap-1.0",
        question_sha256=sha256_file(frozen / "questions.json"),
        cohort_sha256=sha256_file(base / "cohort.json"),
        pinned_files={"design.json": sha256_file(frozen / "design.json")},
    )
    write_new(frozen / "protocol.json", protocol)
    (base / "release.json").write_text("{}", encoding="utf-8")
    before = {p: p.read_bytes() for p in base.rglob("*") if p.is_file()}
    output = tmp_path / "revision"
    revise(base, output)
    assert all(p.read_bytes() == content for p, content in before.items())
    revised = FrozenProtocol.model_validate_json((output / "protocol.json").read_bytes())
    assert revised.version == "heldout-four-modality-ap-1.1"
    assert revised.question_sha256 != protocol.question_sha256
    assert not revised.runtime_approved
    with pytest.raises(FileExistsError):
        revise(base, output)
    (frozen / "questions.json").write_text(old.model_dump_json() + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="BASE_QUESTIONS_CHANGED"):
        revise(base, tmp_path / "invalid")
