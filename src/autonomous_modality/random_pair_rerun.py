"""Exact-two draws and transactional replacement of historical RANDOM records."""

import hashlib
import json
import random
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

MODALITIES = ("CRATER_CATALOG", "MULTISPECTRAL_IMAGE", "OPTICAL_IMAGE", "TOPOGRAPHY")
PAIR_VERSION = "uniform-exact-two-shared-v1"


class ReplacementReceipt(BaseModel):
    """Identify the successful replacement and the preserved original bytes."""

    model_config = ConfigDict(extra="forbid", strict=True)
    version: str = PAIR_VERSION
    original_sha256: str
    replacement_sha256: str
    metadata_sha256: str


def file_digest(path: Path) -> str:
    """Hash a persisted record."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def random_pair(case_id: str, question_id: str, draw_index: int, seed: int = 42) -> list[str]:
    """Match the Gemma exact-two experiment, including replacement between draws."""
    if not case_id.isdecimal() or question_id not in {"Q1", "Q2", "Q3", "Q4"}:
        raise ValueError("Invalid scenario")
    if type(draw_index) is not int or draw_index not in range(5) or type(seed) is not int:
        raise ValueError("Invalid draw index or seed")
    payload = json.dumps([seed, f"{case_id}-{question_id}", 4.0, draw_index], separators=(",", ":"))
    draw_seed = int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")
    return sorted(random.Random(draw_seed).sample(sorted(MODALITIES), 2))


def preserve_bytes(source: Path, backup: Path) -> None:
    """Copy once and verify; never replace a different backup."""
    if source.resolve() == backup.resolve():
        raise ValueError("Backup must be outside the source path")
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        with source.open("rb") as src, backup.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    if file_digest(source) != file_digest(backup):
        raise ValueError(f"Backup differs: {backup}")


def retire_revision_files(folder: Path, backup: Path) -> int:
    """Move only revision attempt files and sidecars out of the active folder."""
    if backup.resolve().is_relative_to(folder.resolve()):
        raise ValueError("Retired files must be outside the active folder")
    paths = sorted(folder.glob("Q*__AGENT_ANSWER_REVISION__r*.json"))
    metadata = folder / "revision_metadata.json"
    if metadata.exists():
        paths.append(metadata)
    for source in paths:
        preserve_bytes(source, backup / source.name)
        source.unlink()
    return len(paths)


def install_random_result(
    destination: Path, candidate: Path, backup: Path, metadata_sha256: str
) -> ReplacementReceipt:
    """Install a validated success at the original filename, after backing it up."""
    new: dict[str, Any] = json.loads(candidate.read_bytes())
    old: dict[str, Any] = json.loads(destination.read_bytes())
    keys = ("model", "case_id", "question_id", "condition", "draw_index", "question")
    if any(new.get(key) != old.get(key) for key in keys):
        raise ValueError("Replacement identity mismatch")
    if new.get("condition") != "RANDOM" or new.get("status") != "success":
        raise ValueError("Only successful RANDOM replacements can be installed")
    if new.get("finish_reason") != "eos" or not new.get("answer", "").strip():
        raise ValueError("Replacement answer is incomplete")
    if new.get("run_sha256") != metadata_sha256:
        raise ValueError("Replacement metadata mismatch")
    if new.get("selected") != random_pair(new["case_id"], new["question_id"], new["draw_index"]):
        raise ValueError("Replacement draw mismatch")
    receipt = ReplacementReceipt(
        original_sha256=file_digest(backup if backup.exists() else destination),
        replacement_sha256=file_digest(candidate),
        metadata_sha256=metadata_sha256,
    )
    if receipt.replacement_sha256 == file_digest(destination) and backup.exists():
        return receipt
    preserve_bytes(destination, backup)
    # Same-folder rename minimizes the interval during which a record is replaced.
    candidate.replace(destination)
    return receipt
