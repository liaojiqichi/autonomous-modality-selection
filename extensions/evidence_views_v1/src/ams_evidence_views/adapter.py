"""Explicit opt-in Qwen-compatible content; no model calls or notebook monkey-patching."""

from pathlib import Path
from typing import Literal

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import local_file

from .models import Manifest, Modality, Record


class Content(Record):
    """Model-compatible image or text block, exported without null properties."""

    type: Literal["text", "image"]
    text: str | None = None
    image: str | None = None


def load_package(root: Path) -> Manifest:
    """Validate an independently relocated package and every output checksum."""
    manifest = Manifest.model_validate_json((root / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest.files:
        path = local_file(root, item.path)
        if path.stat().st_size != item.bytes or sha256_file(path) != item.sha256:
            raise ValueError(f"output checksum mismatch: {item.path}")
    return manifest


def build_content(root: Path, question: str, selected: list[Modality]) -> list[dict[str, str]]:
    """Provide only selected scientific modalities; [] returns question text alone."""
    allowed = {"CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY"}
    if not question.strip() or len(selected) != len(set(selected)) or set(selected) - allowed:
        raise ValueError("empty question, duplicate selection, or unknown modality")
    if not selected:
        return [{"type": "text", "text": question}]
    manifest = load_package(root)
    blocks = [Content(type="text", text=question)]
    captions = {
        "CRATER_CATALOG": "Historical catalogue codes; not expert-validated ground truth. "
        "int_shp: b=bowl, sh=slump hummocks, ff=flat floor; rim_shp: c=circular, "
        "sc=scalloped, t=terraced; cent_struc: cp=central peak, mp=multiple peaks, "
        "pi=central pit, pr=peak ring, mr=multi-ring, n=none; x=poorly imaged. "
        "rayed: y=yes, n=no. Coordinates are degrees; diameter is km.",
        "OPTICAL_IMAGE": "Local and regional optical views, in that order. "
        "Values are stretched display DN, not calibrated reflectance or composition. "
        "Pixel spacing and registration limit interpretation.",
        "TOPOGRAPHY": "Elevation map followed by east and north profiles. "
        "Numeric TIFF and full CSV remain in the package, but are not directly read by the model. "
        "Only the following summary, sampled numbers and images enter this context.",
    }
    # Fixed order independent of selector output order.
    for modality in ["CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY"]:
        if modality not in selected:
            continue
        blocks.append(Content(type="text", text=captions[modality]))
        for item in manifest.files:
            if item.modality != modality or item.kind == "numeric":
                continue
            path = local_file(root, item.path)
            if item.kind == "text":
                blocks.append(Content(type="text", text=path.read_text(encoding="utf-8")))
            else:
                blocks.append(Content(type="image", image=str(path)))
    return [block.model_dump(exclude_none=True) for block in blocks]
