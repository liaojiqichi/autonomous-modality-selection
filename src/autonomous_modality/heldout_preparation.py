"""Read real development snapshots and validate preparation records offline."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from autonomous_modality.heldout_colab import preserve_json
from autonomous_modality.pilot import CatalogueRow


def locate_dataset(directory: Path, archive_path: Path, destination: Path) -> Path:
    """Locate or safely extract a release without replacing existing files."""
    if (directory / "release.json").is_file():
        return directory
    if not destination.exists():
        if not archive_path.is_file():
            raise FileNotFoundError(f"Set DATASET_ROOT or DATASET_ZIP: {archive_path}")
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("DUPLICATE_ARCHIVE_PATH")
            root = destination.resolve()
            for item in archive.infolist():
                if not (root / item.filename).resolve().is_relative_to(root):
                    raise ValueError("UNSAFE_ARCHIVE_PATH")
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("ARCHIVE_SYMLINK")
            destination.mkdir(parents=True, exist_ok=False)
            archive.extractall(destination)
    candidates = list(destination.rglob("release.json"))
    if len(candidates) != 1:
        raise ValueError("Inspect incomplete or ambiguous extraction; no files were overwritten")
    return candidates[0].parent


def development_snapshot(archive_path: Path, output: Path, case_id: int = 16604) -> dict:
    """Copy hash-checked views and recover a catalogue from recorded real input text.

    The historical archive omitted catalogue.json. Recover its JSON value from
    ALL_AVAILABLE messages and record that provenance explicitly.
    """
    if case_id not in {16604, 5031, 2179}:
        raise ValueError("Use one of the three previously inspected development targets")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        receipts = [n for n in names if n.endswith(f"/shared_inputs/{case_id}/receipt.json")]
        if len(receipts) != 1:
            raise ValueError("DEVELOPMENT_SNAPSHOT_MISSING_OR_AMBIGUOUS")
        prefix = receipts[0].rsplit("/", 1)[0] + "/"
        receipt_bytes = archive.read(receipts[0])
        receipt = json.loads(receipt_bytes)
        metadata_names = [
            n for n in names if f"/crater-{case_id}/" in n and n.endswith("run_metadata.json")
        ]
        if len(metadata_names) != 1:
            raise ValueError("AMBIGUOUS_DEVELOPMENT_METADATA")
        assets = json.loads(archive.read(metadata_names[0]))["config"]["assets"]
        expected = {
            "optical_local.png",
            "optical_context.png",
            "elevation.png",
            "profile_east.png",
            "profile_north.png",
            "terrain.txt",
            "multispectral.txt",
        }
        if set(receipt["output_sha256"]) != expected:
            raise ValueError("UNEXPECTED_DEVELOPMENT_SNAPSHOT_FILES")
        payloads = {n: archive.read(prefix + n) for n in expected}
        for name, payload in payloads.items():
            if hashlib.sha256(payload).hexdigest() != receipt["output_sha256"][name]:
                raise ValueError(f"DEVELOPMENT_INPUT_CHANGED: {name}")
        rows = []
        for name in names:
            if f"/crater-{case_id}/" not in name or "__ALL_AVAILABLE__" not in name:
                continue
            record = json.loads(archive.read(name))
            for generation in record.get("answer_generations", []):
                for message in generation["messages"]:
                    for block in message["content"]:
                        if block.get("type") != "text":
                            continue
                        text = block["text"]
                        marker = "Historical catalogue record;"
                        if marker in text:
                            tail = text.split(marker, 1)[1]
                            value, _ = json.JSONDecoder().raw_decode(tail[tail.index("{") :])
                            row = CatalogueRow.model_validate(value)
                            if row.id != case_id:
                                raise ValueError("DEVELOPMENT_CATALOGUE_ID_MISMATCH")
                            rows.append(row.model_dump())
        if not rows or any(row != rows[0] for row in rows):
            raise ValueError("MISSING_OR_CONFLICTING_RECORDED_CATALOGUE")
    payloads["receipt.json"] = receipt_bytes
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        path = output / name
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError(f"EXISTING_DEVELOPMENT_INPUT_CHANGED: {name}")
        else:
            with path.open("xb") as stream:
                stream.write(payload)
    preserve_json(output / "catalogue.json", rows[0])
    return {
        "catalogue": rows[0],
        "receipt": receipt,
        "assets": assets,
        "catalogue_origin": "recorded_all_available_input",
    }


def validate_preparation(record: dict) -> None:
    """Require all planned technical checks, without claiming scientific validation."""
    expected = {
        (q, c)
        for q in ("Q1", "Q2", "Q3", "Q4")
        for c in ("ALL_AVAILABLE", "AGENT", "AGENT_ITERATIVE")
    }
    attempts = record.get("attempts", [])
    if len(attempts) != 12 or {(a["question_id"], a["condition"]) for a in attempts} != expected:
        raise ValueError("INCOMPLETE_DEVELOPMENT_VALIDATION")
    for attempt in attempts:
        if attempt.get("status") != "success" or not attempt.get("answer", "").strip():
            raise ValueError("DEVELOPMENT_FAILURE_REQUIRES_REVIEW")
        logs = attempt.get("generation_log", [])
        if not logs or any(g.get("finish_reason") != "eos" or g.get("error") for g in logs):
            raise ValueError("DEVELOPMENT_GENERATION_NOT_COMPLETE")
    if record.get("split") != "development" or record.get("case_id") not in (16604, 5031, 2179):
        raise ValueError("VALIDATION_MUST_USE_DEVELOPMENT_DATA")
