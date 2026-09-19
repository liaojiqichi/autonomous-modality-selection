"""Strict, portable contracts for an isolated representation experiment."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Modality = Literal["CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Record(BaseModel):
    """Forbid unknown properties and nonfinite persisted values."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Settings(Record):
    """Fixed, task-independent representation policy."""

    version: Literal["evidence-views-1.0"] = "evidence-views-1.0"
    pixels: int = Field(default=960, ge=480, le=1600)
    profile_text_samples: int = Field(default=17, ge=3, le=33)
    profile_policy: Literal["central_pixel_or_mean_of_two; both_valid_required"] = (
        "central_pixel_or_mean_of_two; both_valid_required"
    )


class Product(Record):
    """One output file with modality ownership and original parent hashes."""

    path: str
    modality: Modality
    kind: Literal["image", "text", "numeric"]
    sha256: Digest
    bytes: int = Field(gt=0)
    parents: dict[str, Digest] = Field(min_length=1)


class Manifest(Record):
    """Manifest is written last; its presence marks a completed package."""

    schema_version: Literal["evidence-views-package-1.0"] = "evidence-views-package-1.0"
    settings: Settings
    case_id: int = Field(gt=0)
    case_name: str
    source_package_sha256: Digest
    source_files: dict[str, Digest]
    implementation_sha256: dict[str, Digest]
    software_versions: dict[str, str]
    files: list[Product] = Field(min_length=1)
    expert_approved: Literal[False] = False
    llm_called: Literal[False] = False

    @model_validator(mode="after")
    def validate_products(self) -> Self:
        """Reject duplicate paths and untracked parent data."""
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate output paths")
        for item in self.files:
            if any(self.source_files.get(p) != digest for p, digest in item.parents.items()):
                raise ValueError("unknown or changed parent")
        expected = {
            "catalogue.json": ("CRATER_CATALOG", "text"),
            "optical_local.png": ("OPTICAL_IMAGE", "image"),
            "optical_context.png": ("OPTICAL_IMAGE", "image"),
            "dem_numeric.tif": ("TOPOGRAPHY", "numeric"),
            "elevation.png": ("TOPOGRAPHY", "image"),
            "terrain_summary.json": ("TOPOGRAPHY", "numeric"),
            "terrain.txt": ("TOPOGRAPHY", "text"),
            "profile_east.csv": ("TOPOGRAPHY", "numeric"),
            "profile_north.csv": ("TOPOGRAPHY", "numeric"),
            "profile_east.png": ("TOPOGRAPHY", "image"),
            "profile_north.png": ("TOPOGRAPHY", "image"),
        }
        if {item.path: (item.modality, item.kind) for item in self.files} != expected:
            raise ValueError("incomplete or mislabelled representation package")
        return self


class Profile(Record):
    """Full raster cross-section, not an inferred crater-depth measurement."""

    axis: Literal["east", "north"]
    distance_km: list[float]
    elevation_m: list[float | None]


class TerrainSummary(Record):
    """Statistics refer to the entire crop and retain source metadata."""

    shape: list[int]
    crs_wkt: str
    transform: list[float]
    source_units: str
    source_scale: float
    source_offset: float
    valid_fraction: float = Field(ge=0, le=1)
    minimum_m: float
    maximum_m: float
    mean_m: float
    std_m: float
    profiles: list[Profile]
