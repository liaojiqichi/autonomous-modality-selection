"""Read-only bridge to existing evidence_views_v1 packages, without copying data."""

from pathlib import Path

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.iterative import ContentBlock, EvidenceObservation, LoadEvidence
from autonomous_modality.models import InputDataModality


def evidence_view_loader(root: Path, *, expected_case_id: int) -> LoadEvidence:
    """Pin and verify a real package; add the extension's src directory to sys.path first.

    Only requested content reaches the model. Whole-package integrity checks read
    other files locally but never expose their contents in the model messages.
    """
    from ams_evidence_views.adapter import build_content, load_package

    root = root.resolve()
    manifest_path = root / "manifest.json"
    manifest_hash = sha256_file(manifest_path)
    manifest = load_package(root)
    if manifest.case_id != expected_case_id:
        raise ValueError("evidence package belongs to a different crater")

    def load(modality: InputDataModality) -> EvidenceObservation:
        if modality.value not in {"CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY"}:
            raise ValueError("modality is not present in the evidence-view package")
        if sha256_file(manifest_path) != manifest_hash:
            raise ValueError("evidence manifest changed during acquisition")
        content = build_content(root, "Requested evidence follows.", [modality.value])[1:]
        # Recheck after reading: a changed package cannot silently enter the trace.
        load_package(root)
        if sha256_file(manifest_path) != manifest_hash:
            raise ValueError("evidence manifest changed during acquisition")
        return EvidenceObservation(
            modality=modality,
            blocks=[ContentBlock.model_validate(block) for block in content],
            evidence_sha256={
                item.path: item.sha256
                for item in manifest.files
                if item.modality == modality.value and item.kind != "numeric"
            },
            package_sha256=manifest_hash,
        )

    return load
