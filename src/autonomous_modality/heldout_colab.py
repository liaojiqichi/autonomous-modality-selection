"""Read-only formal data adaptation, batch allocation and explicit deployment approval."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Literal

from pydantic import Field

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.benchmark import QuestionSet
from autonomous_modality.heldout import Cohort
from autonomous_modality.heldout_finalize import verify_files, verify_release
from autonomous_modality.heldout_protocol import MODELS, Design, FrozenProtocol, freeze_design
from autonomous_modality.models import StrictModel


class Revision(StrictModel):
    version: Literal["question-only-revision-20261016"]
    base_release: str
    base_release_sha256: str
    base_protocol_sha256: str
    base_question_sha256: str
    files: dict[str, str]
    inherits: str
    changes: str
    runtime_approved: Literal[False]
    model_inference_performed: Literal[False]


class Deployment(StrictModel):
    model_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    processor_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    environment: dict[str, str] = Field(min_length=4)
    image_processor_size: dict[str, int]
    image_processor_config: dict = Field(default_factory=dict)
    validation_file: str
    validation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    validation_split: Literal["development"]
    reviewed_pass: Literal[True]
    validation_notes: str = Field(min_length=10)


class RuntimeApproval(StrictModel):
    version: Literal["heldout-runtime-approval-1"]
    approved_by: str = Field(min_length=1)
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    notebook_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    models: dict[str, Deployment]


class FormalContext(StrictModel):
    cohort: Cohort
    questions: QuestionSet
    design: Design
    protocol: FrozenProtocol

    def batch_ids(self, batch: int) -> list[int]:
        """Use the frozen cohort order; batching does not resample targets."""
        if type(batch) is not int or not 1 <= batch <= 5:
            raise ValueError("BATCH_MUST_BE_1_TO_5")
        return [t.id for t in self.cohort.targets[(batch - 1) * 6 : batch * 6]]

    def random_choice(self, case_id: str, question_id: str, budget: int, draw: int) -> list[str]:
        """Return an existing shared draw without invoking an RNG."""
        if type(draw) is not int or draw not in range(5) or budget not in (3, 4):
            raise ValueError("INVALID_FROZEN_DRAW")
        matches = [
            s
            for s in self.design.scenarios
            if str(s.case_id) == case_id and s.question_id == question_id
        ]
        if len(matches) != 1:
            raise ValueError("UNKNOWN_FORMAL_SCENARIO")
        return list(getattr(matches[0], f"random_budget_{budget}")[draw])


def load_context(base: Path, overlay: Path) -> FormalContext:
    """Verify the original release and the question-only overlay before inference."""
    revision = Revision.model_validate_json((overlay / "revision.json").read_bytes())
    verify_files(overlay, revision.files)
    if sha256_file(base / "release.json") != revision.base_release_sha256:
        raise ValueError("WRONG_FORMAL_DATA_RELEASE")
    if sha256_file(base / "frozen/protocol.json") != revision.base_protocol_sha256:
        raise ValueError("BASE_PROTOCOL_CHANGED")
    verify_release(base)
    protocol = FrozenProtocol.model_validate_json((overlay / "protocol.json").read_bytes())
    verify_files(overlay, protocol.pinned_files)
    if sha256_file(overlay / "questions.json") != protocol.question_sha256:
        raise ValueError("QUESTION_HASH_CHANGED")
    if sha256_file(overlay / "cohort.json") != protocol.cohort_sha256:
        raise ValueError("COHORT_HASH_CHANGED")
    context = FormalContext(
        cohort=Cohort.model_validate_json((overlay / "cohort.json").read_bytes()),
        questions=QuestionSet.model_validate_json((overlay / "questions.json").read_bytes()),
        design=Design.model_validate_json((overlay / "design.json").read_bytes()),
        protocol=protocol,
    )
    if context.cohort != Cohort.model_validate_json((base / "cohort.json").read_bytes()):
        raise ValueError("COHORT_DIFFERS_FROM_RELEASE")
    if freeze_design(context.cohort, context.questions) != context.design:
        raise ValueError("FROZEN_DESIGN_CHANGED")
    return context


def load_approval(
    path: Path, overlay: Path, notebook: Path, model_id: str | None = None
) -> RuntimeApproval:
    """Verify approvals; an explicit model permits independently validated deployments."""
    approval = RuntimeApproval.model_validate_json(path.read_bytes())
    if model_id is None and set(approval.models) != set(MODELS):
        raise ValueError("BOTH_MODEL_APPROVALS_REQUIRED")
    if model_id is not None and (model_id not in MODELS or set(approval.models) != {model_id}):
        raise ValueError("SELECTED_MODEL_APPROVAL_REQUIRED")
    if approval.protocol_sha256 != sha256_file(overlay / "protocol.json"):
        raise ValueError("APPROVAL_PROTOCOL_CHANGED")
    if approval.notebook_sha256 != sha256_file(notebook):
        raise ValueError("APPROVAL_NOTEBOOK_CHANGED")
    for deployment in approval.models.values():
        verify_files(path.parent, {deployment.validation_file: deployment.validation_sha256})
        if not {"torch", "transformers", "bitsandbytes", "accelerate", "Pillow"}.issubset(
            deployment.environment
        ):
            raise ValueError("INCOMPLETE_RUNTIME_VERSIONS")
    return approval


def frozen_prompts(base: Path) -> ModuleType:
    """Import only the hash-verified frozen policy, not mutable development prompts."""
    path = base / "frozen/selector_and_answer_prompts.py"
    protocol = FrozenProtocol.model_validate_json((base / "frozen/protocol.json").read_bytes())
    if sha256_file(path) != protocol.pinned_files[path.name]:
        raise ValueError("FROZEN_PROMPTS_CHANGED")
    spec = importlib.util.spec_from_file_location("ams_formal_frozen_prompts", path)
    if spec is None or spec.loader is None:
        raise ValueError("FROZEN_PROMPTS_UNLOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preserve_json(path: Path, value: dict) -> None:
    """Keep a shared lock immutable across models, batches and sessions."""
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError(f"FORMAL_LOCK_CHANGED: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
