"""Synthetic offline preparation tests; no planetary data or model inference."""

import json
import zipfile
from pathlib import Path

import pytest

from autonomous_modality.heldout_preparation import locate_dataset, validate_preparation


def test_dataset_archive_and_existing_directory(tmp_path: Path) -> None:
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("dataset/release.json", "{}")
    root = locate_dataset(tmp_path / "absent", archive, tmp_path / "extracted")
    assert root == tmp_path / "extracted/dataset"
    assert locate_dataset(root, archive, tmp_path / "other") == root
    assert locate_dataset(tmp_path / "absent", archive, tmp_path / "extracted") == root


def test_unsafe_zip(tmp_path: Path) -> None:
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape", "bad")
    with pytest.raises(ValueError, match="UNSAFE"):
        locate_dataset(tmp_path / "absent", archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_missing_or_partial_dataset(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="DATASET_ROOT"):
        locate_dataset(tmp_path, tmp_path / "missing.zip", tmp_path / "out")
    (tmp_path / "out").mkdir()
    with pytest.raises(ValueError, match="incomplete"):
        locate_dataset(tmp_path, tmp_path / "missing.zip", tmp_path / "out")


def validation() -> dict:
    return {
        "split": "development",
        "case_id": 16604,
        "attempts": [
            {
                "question_id": q,
                "condition": c,
                "status": "success",
                "answer": "Synthetic validation only",
                "generation_log": [{"finish_reason": "eos", "error": None}],
            }
            for q in ("Q1", "Q2", "Q3", "Q4")
            for c in ("ALL_AVAILABLE", "AGENT", "AGENT_ITERATIVE")
        ],
    }


def test_complete_validation() -> None:
    validate_preparation(validation())


@pytest.mark.parametrize(
    "failure", ["truncated", "error", "empty", "heldout", "selector_length", "missing"]
)
def test_invalid_validation(failure: str) -> None:
    record = validation()
    if failure in ("error", "truncated"):
        record["attempts"][0]["status"] = failure
    elif failure == "empty":
        record["attempts"][0]["answer"] = ""
    elif failure == "heldout":
        record["case_id"] = 2305
    elif failure == "missing":
        record["attempts"].pop()
    else:
        record["attempts"][0]["generation_log"][0]["finish_reason"] = "length"
    with pytest.raises(ValueError):
        validate_preparation(record)


def test_runtime_amendment_hash() -> None:
    from autonomous_modality.acquisition import sha256_file

    root = Path("configs/heldout_runtime_revision_20261016")
    revision = json.loads((root / "revision.json").read_text())
    assert sha256_file(root / "prompts.py") == revision["prompt_sha256"]


def test_real_snapshot_adapter_with_synthetic_archive(tmp_path: Path) -> None:
    import hashlib

    from autonomous_modality.heldout_preparation import development_snapshot

    row = dict(
        id=16604,
        name="SYNTHETIC",
        lat_n=0.0,
        lon_e_0=0.0,
        diameter=10.0,
        int_shp="x",
        rim_shp="x",
        cent_struc="x",
        rayed="n",
    )
    files = {
        n: b"SYNTHETIC"
        for n in (
            "optical_local.png",
            "optical_context.png",
            "elevation.png",
            "profile_east.png",
            "profile_north.png",
            "terrain.txt",
            "multispectral.txt",
        )
    }
    archive = tmp_path / "development.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name, payload in files.items():
            z.writestr("dev/shared_inputs/16604/" + name, payload)
        z.writestr(
            "dev/shared_inputs/16604/receipt.json",
            json.dumps(
                {"output_sha256": {n: hashlib.sha256(p).hexdigest() for n, p in files.items()}}
            ),
        )
        z.writestr("dev/crater-16604/run_metadata.json", '{"config":{"assets":{}}}')
        z.writestr(
            "dev/crater-16604/Q1__ALL_AVAILABLE__r01.json",
            json.dumps(
                {
                    "answer_generations": [
                        {
                            "messages": [
                                {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Historical catalogue record; fixture\n"
                                            + json.dumps(row),
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ),
        )
    out = tmp_path / "out"
    assert development_snapshot(archive, out)["catalogue"] == row
    development_snapshot(archive, out)
    (out / "terrain.txt").write_text("tampered")
    with pytest.raises(ValueError, match="EXISTING_DEVELOPMENT"):
        development_snapshot(archive, out)
    with pytest.raises(ValueError, match="development targets"):
        development_snapshot(archive, out, 2305)


def test_preparation_cell_resume_and_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import copy
    import importlib.metadata
    import shutil
    import sys
    from types import SimpleNamespace

    import test_colab_four_modality as four
    import test_colab_notebook as base
    from autonomous_modality import development_inputs
    from autonomous_modality.acquisition import sha256_file
    from autonomous_modality.heldout_colab import load_approval, preserve_json
    from test_heldout_colab import BOOK, template_sources

    ns = four.runtime.__wrapped__(tmp_path, monkeypatch)
    old_views = ns["VIEW_DIR"]
    old_receipt = copy.deepcopy(ns["receipt"].__dict__)
    assets = copy.deepcopy(ns["ASSETS"])
    row = ns["catalogue"].model_dump()
    row["id"] = 16604

    def snapshot(archive: Path, output: Path) -> dict:
        output.mkdir(parents=True, exist_ok=True)
        for name in old_receipt["output_sha256"]:
            shutil.copy2(old_views / name, output / name)
        (output / "receipt.json").write_text(json.dumps(old_receipt))
        (output / "catalogue.json").write_text(json.dumps(row))
        return dict(catalogue=row, receipt=old_receipt, assets=assets, catalogue_origin="SYNTHETIC")

    def run_cell(source: str, store_history: bool) -> SimpleNamespace:
        base.execute(source, ns)
        return SimpleNamespace(raise_error=lambda: None)

    monkeypatch.setitem(
        sys.modules,
        "IPython",
        SimpleNamespace(get_ipython=lambda: SimpleNamespace(run_cell=run_cell)),
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "fixture")
    ns.update(template_sources())
    ns.update(
        MODE="prepare",
        PROJECT=Path.cwd(),
        MODEL_ID="google/gemma-4-E4B-it",
        PREPARATION_DIR=tmp_path / "approval/gemma/validation-001",
        APPROVAL_DIR=tmp_path / "approval",
        APPROVAL_PATH=tmp_path / "approval/gemma.json",
        OVERLAY=Path("configs/heldout_question_revision_20261016"),
        FORMAL_NOTEBOOK=BOOK,
        AMENDMENT_PATH=Path("configs/heldout_runtime_revision_20261016/revision.json"),
        DEV_RESULTS_ZIP=BOOK,
        FROZEN_PROMPTS=development_inputs,
        DEPLOYMENT=SimpleNamespace(model_revision="a" * 40, processor_revision="a" * 40),
        processor=SimpleNamespace(image_processor=SimpleNamespace(to_json_string=lambda: "{}")),
        torch=SimpleNamespace(
            manual_seed=lambda seed: None,
            version=SimpleNamespace(cuda="fixture"),
            cuda=SimpleNamespace(
                manual_seed_all=lambda seed: None,
                empty_cache=lambda: None,
                get_device_name=lambda index: "fixture",
            ),
        ),
        importlib=importlib,
        SimpleNamespace=SimpleNamespace,
        sha256_file=sha256_file,
        preserve_json=preserve_json,
        development_snapshot=snapshot,
        validate_preparation=validate_preparation,
    )
    cells = ["".join(c["source"]) for c in json.loads(BOOK.read_text())["cells"]]
    prep = next(s for s in cells if "snapshot = development_snapshot" in s)
    approve = next(s for s in cells if "CONFIRM_DEVELOPMENT_REVIEW = False" in s)
    base.execute(prep, ns)
    saved = ns["PREPARATION_DIR"] / "validation.json"
    before = saved.read_bytes()
    validate_preparation(json.loads(before))
    base.execute(prep, ns)
    assert saved.read_bytes() == before
    base.execute(approve, ns)
    assert not ns["APPROVAL_PATH"].exists()
    base.execute(
        approve.replace("CONFIRM_DEVELOPMENT_REVIEW = False", "CONFIRM_DEVELOPMENT_REVIEW = True"),
        ns,
    )
    approval = load_approval(ns["APPROVAL_PATH"], ns["OVERLAY"], BOOK, ns["MODEL_ID"])
    assert set(approval.models) == {ns["MODEL_ID"]}
    with pytest.raises(ValueError, match="SELECTED_MODEL"):
        load_approval(ns["APPROVAL_PATH"], ns["OVERLAY"], BOOK, "Qwen/Qwen3-VL-8B-Instruct")
