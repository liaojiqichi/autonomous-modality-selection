"""Offline language and provenance checks for maintained project text."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from autonomous_modality.benchmark import QuestionSet, ReviewSet
from autonomous_modality.development_inputs import ANSWER_POLICY
from autonomous_modality.iterative import PROMPT_VERSION, SELECTOR_INSTRUCTIONS

ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af]")
TEXT_SUFFIXES = {".py", ".md", ".html", ".json", ".yaml", ".yml", ".toml", ".ipynb"}


def test_maintained_project_text_contains_no_chinese() -> None:
    """Inspect maintained sources, including decoded JSON, without reading real data."""
    paths = [ROOT / name for name in ("README.md", "AGENTS.md", "pyproject.toml")]
    for name in ("configs", "docs", "examples", "notebooks", "src", "tests", "extensions"):
        paths.extend(
            p
            for p in (ROOT / name).rglob("*")
            if p.is_file()
            and p.suffix in TEXT_SUFFIXES
            and not {"__pycache__", "_checks", ".pytest_cache", ".ruff_cache"}.intersection(p.parts)
        )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert not HAN.search(text), str(path.relative_to(ROOT))
        if path.suffix in {".json", ".ipynb"}:
            decoded = json.dumps(json.loads(text), ensure_ascii=False)
            assert not HAN.search(decoded), str(path.relative_to(ROOT))


@pytest.mark.parametrize("version", [1, 2])
def test_english_questions_and_legacy_versions_remain_readable(version: int) -> None:
    """Translation gets a new version while historical configuration stays readable."""
    payload = json.loads(
        (ROOT / f"configs/mercury_questions_v{version}.json").read_text(encoding="utf-8")
    )
    translated = QuestionSet.model_validate(payload)
    assert translated.version == f"mercury-questions-{version}.0-en.1"
    assert len(translated.questions) == (4 if version == 1 else 7)
    payload["version"] = f"mercury-questions-{version}.0"
    assert QuestionSet.model_validate(payload).questions == translated.questions
    payload["version"] = "unknown-language-version"
    with pytest.raises(ValidationError):
        QuestionSet.model_validate(payload)


def test_translated_reviews_preserve_screening_statuses() -> None:
    """Translate historical descriptions without promoting held or provisional cases."""
    payload = json.loads(
        (ROOT / "configs/mercury_visual_reviews_v1.json").read_text(encoding="utf-8")
    )
    reviews = ReviewSet.model_validate(payload)
    assert reviews.version == "visual-review-1.0-en.1"
    assert {r.case_id for r in reviews.reviews if r.status == "hold"} == {
        734,
        4512,
        6611,
        1695,
        908,
    }
    assert len(reviews.reviews) == 12
    payload["version"] = "visual-review-1.0"
    assert ReviewSet.model_validate(payload).reviews == reviews.reviews
    payload["version"] = "unknown-language-version"
    with pytest.raises(ValidationError):
        ReviewSet.model_validate(payload)


def test_language_policy_is_explicit_and_versioned() -> None:
    """Both selector interfaces and the shared answer policy explicitly request English."""
    notebook = json.loads(
        (ROOT / "notebooks/autonomous_modality_selection_iterative.ipynb").read_text(
            encoding="utf-8"
        )
    )
    source = "\n".join("".join(c["source"]) for c in notebook["cells"])
    assert "Write entirely in English, aiming for 200-300 words" in ANSWER_POLICY
    assert "ANSWER_POLICY_VERSION" in source
    assert "Write the rationale entirely in English." in source
    assert '"language": "en"' in source
    assert '"language_protocol": "english-ap-1.0"' in source
    assert "colab-ap-agentic-development-en-5" in source
    assert PROMPT_VERSION == "bounded-evidence-selector-ap-1.2-compact"
    assert "Write all free-text fields entirely in English." in SELECTOR_INSTRUCTIONS
    assert "Answer in Chinese" not in source


def exporter() -> ModuleType:
    """Load the standalone exporter without running its CLI."""
    spec = importlib.util.spec_from_file_location(
        "notebook_exporter", ROOT / "examples/upgrade_colab_notebook.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_preserves_source_and_refuses_overwrite(tmp_path: Path) -> None:
    """Source cells/settings are never executed or copied into the canonical template."""
    source = tmp_path / "original.ipynb"
    original = b'{"cells": [], "metadata": {"private_fixture": "DO_NOT_COPY"}}'
    source.write_bytes(original)
    output = tmp_path / "english.ipynb"
    module = exporter()
    module.export_notebook(output, source)
    assert source.read_bytes() == original
    exported = json.loads(output.read_text(encoding="utf-8"))
    assert exported["metadata"]["source_notebook_sha256"] == hashlib.sha256(original).hexdigest()
    assert (
        exported["metadata"]["template_sha256"]
        == hashlib.sha256(module.TEMPLATE.read_bytes()).hexdigest()
    )
    assert "DO_NOT_COPY" not in output.read_text(encoding="utf-8")
    for cell in exported["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        module.export_notebook(output, source)
    assert output.read_bytes() == before
    with pytest.raises(FileExistsError):
        module.export_notebook(source, source)
    assert source.read_bytes() == original


@pytest.mark.parametrize("payload", ["[]", "{}", '{"cells": null}', "invalid JSON"])
def test_export_rejects_invalid_source(tmp_path: Path, payload: str) -> None:
    """Invalid provenance sources must not produce a misleading output notebook."""
    source, output = tmp_path / "invalid.ipynb", tmp_path / "output.ipynb"
    source.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        exporter().export_notebook(output, source)
    assert not output.exists()


def test_export_without_source(tmp_path: Path) -> None:
    """The English template can be exported without the obsolete original notebook."""
    output = tmp_path / "english.ipynb"
    exporter().export_notebook(output)
    metadata = json.loads(output.read_text(encoding="utf-8"))["metadata"]
    assert metadata["export_protocol"] == "english-template-1.0"
    assert "source_notebook_sha256" not in metadata
