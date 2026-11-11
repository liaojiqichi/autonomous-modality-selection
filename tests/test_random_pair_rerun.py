"""Verify exact-two sampling and preservation without model inference or real data."""

import ast
import json
from pathlib import Path

import pytest

from autonomous_modality.random_pair_rerun import (
    file_digest,
    install_random_result,
    random_pair,
    retire_revision_files,
)


def test_pair_sampling_is_shared_deterministic_and_exact_two() -> None:
    assert random_pair("1061", "Q1", 0) == ["MULTISPECTRAL_IMAGE", "TOPOGRAPHY"]
    draws = [random_pair(str(target), "Q1", i) for target in range(100) for i in range(5)]
    assert all(len(set(draw)) == 2 and draw == sorted(draw) for draw in draws)
    assert len({tuple(draw) for draw in draws}) == 6
    assert random_pair("42", "Q2", 3) == random_pair("42", "Q2", 3)


@pytest.mark.parametrize(
    "case,q,draw", [("", "Q1", 0), ("1", "Q5", 0), ("1", "Q1", 5), ("1", "Q1", True)]
)
def test_invalid_draw(case: str, q: str, draw: int) -> None:
    with pytest.raises(ValueError):
        random_pair(case, q, draw)


def fixture_records(tmp_path: Path) -> tuple[Path, Path, Path]:
    folder = tmp_path / "active"
    folder.mkdir()
    destination = folder / "Q1__RANDOM__r01.json"
    candidate = folder / "candidate.tmp"
    backup = tmp_path / "retired" / destination.name
    original = dict(
        model="qwen",
        case_id="1",
        question_id="Q1",
        condition="RANDOM",
        draw_index=0,
        question="Test?",
        selected=["TOPOGRAPHY"],
        answer="old",
    )
    destination.write_text(json.dumps(original))
    candidate.write_text(
        json.dumps(
            dict(
                original,
                selected=random_pair("1", "Q1", 0),
                status="success",
                finish_reason="eos",
                answer="new",
                run_sha256="new-metadata",
            )
        )
    )
    return destination, candidate, backup


def test_success_replaces_only_random_and_keeps_original(tmp_path: Path) -> None:
    destination, candidate, backup = fixture_records(tmp_path)
    baseline = destination.parent / "Q1__AGENT__r01.json"
    baseline.write_bytes(b"baseline unchanged")
    original = destination.read_bytes()
    result = install_random_result(destination, candidate, backup, "new-metadata")
    assert backup.read_bytes() == original
    assert json.loads(destination.read_bytes())["answer"] == "new"
    assert result.replacement_sha256 == file_digest(destination)
    assert baseline.read_bytes() == b"baseline unchanged"
    assert not candidate.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"status": "truncated"},
        {"finish_reason": "length"},
        {"condition": "AGENT"},
        {"case_id": "2"},
        {"selected": ["TOPOGRAPHY"]},
        {"run_sha256": "wrong"},
    ],
)
def test_reject_invalid_replacement_without_touching_old(tmp_path: Path, change: dict) -> None:
    destination, candidate, backup = fixture_records(tmp_path)
    before = destination.read_bytes()
    new = json.loads(candidate.read_bytes())
    candidate.write_text(json.dumps(new | change))
    with pytest.raises(ValueError):
        install_random_result(destination, candidate, backup, "new-metadata")
    assert destination.read_bytes() == before
    assert not backup.exists()


def test_conflicting_backup_blocks_overwrite(tmp_path: Path) -> None:
    destination, candidate, backup = fixture_records(tmp_path)
    backup.parent.mkdir()
    backup.write_bytes(b"different original")
    before = destination.read_bytes()
    with pytest.raises(ValueError, match="Backup differs"):
        install_random_result(destination, candidate, backup, "new-metadata")
    assert destination.read_bytes() == before


def test_revision_move_is_resumable_and_preserves_other_conditions(tmp_path: Path) -> None:
    active, retired = tmp_path / "active", tmp_path / "retired"
    active.mkdir()
    for name in [
        "Q1__AGENT_ANSWER_REVISION__r01.json",
        "Q1__AGENT_ANSWER_REVISION__r01.started.json",
        "Q1__AGENT__r01.json",
    ]:
        (active / name).write_text(name)
    assert retire_revision_files(active, retired) == 2
    assert retire_revision_files(active, retired) == 0
    assert (active / "Q1__AGENT__r01.json").exists()
    assert len(list(retired.iterdir())) == 2
    with pytest.raises(ValueError):
        retire_revision_files(active, active / "backup")


def test_notebook_is_clean_self_contained_and_uses_archived_model_cells() -> None:
    root = Path(__file__).parents[1]
    notebook = json.loads(
        (root / "notebooks/qwen_heldout_random_exact_two_resume.ipynb").read_text(encoding="utf-8")
    )
    sources = []
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            source = "".join(cell["source"])
            ast.parse(source)
            sources.append(source)
    helper = (root / "src/autonomous_modality/random_pair_rerun.py").read_text()
    helper_tree = ast.dump(ast.parse(helper))
    assert any(ast.dump(ast.parse(s)) == helper_tree for s in sources)
    runner = sources[-2]
    assert "for BATCH_NUMBER, TARGET_ID in ALL_TARGETS:" in runner
    assert 'if old.get("run_sha256") == random_hash:' in runner
    assert "run_target_revisions(" not in "\n".join(sources)
