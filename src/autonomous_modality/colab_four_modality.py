"""Verified portable four-modality downloads and compact Colab model inputs."""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.request import urlopen

from PIL import Image

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.multispectral import multispectral_loader
from autonomous_modality.multispectral_dataset import FourModalityManifest
from autonomous_modality.multispectral_release import verify_release

DATASET_NAME = "mercury-four-modality-20261006"
ARCHIVE_SHA256 = "f0b0e0c3fe57459e5f2a09a7909e6a318b9c4be81a1240c249ce31ec34190cae"
ARCHIVE_BYTES = 291730382
DATASET_URL = (
    "https://github.com/liaojiqichi/autonomous-modality-selection/releases/download/"
    "mercury-four-modality-20261006/mercury-four-modality-20261006.zip"
)


def download_archive(destination: Path) -> Path:
    """Download the pinned public release; never overwrite an existing different archive."""
    if not destination.exists():
        partial = destination.with_suffix(".partial")
        with urlopen(DATASET_URL, timeout=120) as response, partial.open("xb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
                if stream.tell() > ARCHIVE_BYTES:
                    raise ValueError("DATASET_DOWNLOAD_TOO_LARGE")
        if partial.stat().st_size != ARCHIVE_BYTES or sha256_file(partial) != ARCHIVE_SHA256:
            raise ValueError("DATASET_DOWNLOAD_CHECKSUM_MISMATCH")
        partial.rename(destination)
    if sha256_file(destination) != ARCHIVE_SHA256:
        raise ValueError("EXISTING_ARCHIVE_DIFFERS")
    return destination


def safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Validate paths, sizes and file types before extraction."""
    members = archive.infolist()
    if sum(m.file_size for m in members) > 2_000_000_000:
        raise ValueError("ARCHIVE_UNPACKED_SIZE_LIMIT")
    names = set()
    for member in members:
        name = member.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or PureWindowsPath(name).drive
            or ".." in path.parts
            or not path.parts
            or path.parts[0] != DATASET_NAME
            or stat.S_ISLNK(member.external_attr >> 16)
            or name in names
        ):
            raise ValueError("UNSAFE_DATASET_ARCHIVE")
        names.add(name)
        member.filename = name
    return members


def extract_dataset(archive_path: Path, parent: Path) -> Path:
    """Extract a pinned archive once and verify every released artifact."""
    if sha256_file(archive_path) != ARCHIVE_SHA256:
        raise ValueError("DATASET_ARCHIVE_CHECKSUM_MISMATCH")
    root = parent / DATASET_NAME
    if root.exists():
        verify_release(root)
        return root
    with zipfile.ZipFile(archive_path) as archive:
        members = safe_members(archive)
        archive.extractall(parent, members=members)
    verify_release(root)
    return root


def prepare_compact_inputs(root: Path, output: Path, edge: int) -> dict:
    """Resize existing core views and verify spectral evidence without changing source data."""
    if not 224 <= edge <= 960:
        raise ValueError("IMAGE_EDGE_OUT_OF_RANGE")
    manifest = FourModalityManifest.model_validate_json((root / "manifest.json").read_bytes())
    spec = {
        "version": "four-modality-compact-1.0",
        "source_sha256": manifest.files,
        "implementation_sha256": {"colab_four_modality.py": sha256_file(Path(__file__))},
        "image_edge": edge,
    }
    receipt_path = output / "receipt.json"
    for name, digest in manifest.files.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256_file(path) != digest:
            raise ValueError("SOURCE_PACKAGE_CHANGED")
    if not manifest.technical_pass:
        raise ValueError("SOURCE_PACKAGE_QA_FAILED")
    if output.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if {k: v for k, v in receipt.items() if k != "output_sha256"} != spec:
            raise ValueError("COMPACT_INPUTS_CHANGED_USE_NEW_RUN_LABEL")
        for name, digest in receipt["output_sha256"].items():
            if sha256_file(output / name) != digest:
                raise ValueError("COMPACT_INPUT_FILE_CHANGED")
        return receipt
    output.mkdir(parents=True, exist_ok=False)
    names = [
        "optical_local.png",
        "optical_context.png",
        "elevation.png",
        "profile_east.png",
        "profile_north.png",
    ]
    for name in names:
        with Image.open(root / "core_views" / name) as image:
            image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            image.save(output / name)
    (output / "terrain.txt").write_bytes((root / "core_views/terrain.txt").read_bytes())
    # Pin the exact same numeric package for selector observations and final answers.
    observation = multispectral_loader(
        root / "summary.json",
        expected_case_id=str(manifest.case_id),
        source_path=root / "multispectral.npz",
    )
    from autonomous_modality.models import InputDataModality

    text = observation(InputDataModality.MULTISPECTRAL_IMAGE).blocks[0].text
    (output / "multispectral.txt").write_text(text, encoding="utf-8")
    names += ["terrain.txt", "multispectral.txt"]
    receipt = {**spec, "output_sha256": {name: sha256_file(output / name) for name in names}}
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    return receipt
