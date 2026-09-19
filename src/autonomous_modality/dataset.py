"""Small target manifests; reuse catalogue and never copy or download rasters."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from autonomous_modality.models import NonEmptyString, StrictModel


class TargetSplit(StrictModel):
    """Human-reviewed target allocation, not inferred from successful model outputs."""

    version: Literal["target-split-1.0"] = "target-split-1.0"
    reviewer: NonEmptyString
    development_ids: list[int] = Field(min_length=6, max_length=6)
    held_out_ids: list[int] = Field(min_length=30, max_length=30)
    inspected_ids: list[int]
    approved: Literal[True]

    @model_validator(mode="after")
    def validate_targets(self) -> Self:
        """Reject overlap, duplicates and previously inspected held-out targets."""
        joined = self.development_ids + self.held_out_ids
        if any(i <= 0 for i in joined) or len(set(joined)) != len(joined):
            raise ValueError("target IDs must be positive, unique and disjoint")
        if set(self.held_out_ids) & set(self.inspected_ids):
            raise ValueError("inspected targets cannot be held out")
        return self


def historical_target_ids(root: Path) -> set[int]:
    """Conservatively mark all crater directories in earlier experiments as seen."""
    return {
        int(path.name.removeprefix("crater-"))
        for path in root.rglob("crater-*")
        if path.is_dir() and path.name.removeprefix("crater-").isdigit()
    }
