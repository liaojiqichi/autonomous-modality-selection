"""Explicit, create-only downloads with checksums for the real-data pilot."""

from __future__ import annotations

import argparse
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.request import Request, urlopen

from pydantic import Field, HttpUrl, model_validator

from autonomous_modality.models import NonEmptyString, StrictModel


class SourceSpec(StrictModel):
    """A versioned public source selected explicitly for acquisition."""

    source_id: NonEmptyString
    url: HttpUrl
    filename: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*[a-zA-Z0-9_]$")]
    expected_bytes: Annotated[int, Field(gt=0)]
    format: Literal["csv", "text", "tiff"]
    citation: NonEmptyString


class DownloadRecord(StrictModel):
    """Provenance of a complete downloaded file; never a metadata fixture."""

    schema_version: Literal["acquisition-1.0"] = "acquisition-1.0"
    source: SourceSpec
    retrieved_utc: datetime
    path: NonEmptyString
    bytes: Annotated[int, Field(gt=0)]
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    etag: str | None = None
    last_modified: str | None = None

    @model_validator(mode="after")
    def validate_size(self) -> Self:
        """A complete receipt must match its pinned source size."""
        if self.bytes != self.source.expected_bytes:
            raise ValueError("receipt bytes must match expected source size")
        return self


SOURCES = (
    SourceSpec(
        source_id="herrick-2011-catalog",
        url="https://drive.google.com/uc?export=download&id=1e5UwToruFpV3UJ9Hnt_1ANrzcpWk3UxQ",
        filename="herrick_2011.csv",
        expected_bytes=564385,
        format="csv",
        citation=(
            "Herrick, Curran & Baer (2011), doi:10.1016/j.icarus.2011.06.021; author's public CSV"
        ),
    ),
    SourceSpec(
        source_id="herrick-2011-readme",
        url="https://drive.google.com/uc?export=download&id=12yjdG4QnPKiGu3kw8ULAqQu9bfwY1RtZ",
        filename="herrick_2011_README.txt",
        expected_bytes=2352,
        format="text",
        citation="Author-provided README for Herrick et al. (2011) catalogue",
    ),
    SourceSpec(
        source_id="usgs-dem-v2",
        url="https://planetarymaps.usgs.gov/mosaic/Mercury_Messenger_USGS_DEM_Global_665m_v2.tif",
        filename="mercury_dem_665m_v2.tif",
        expected_bytes=530934581,
        format="tiff",
        citation="USGS Mercury MESSENGER Global DEM 665m, version 2; Becker et al. (2016)",
    ),
    SourceSpec(
        source_id="mdis-loi-v1",
        url="https://planetarymaps.usgs.gov/mosaic//Mercury_MESSENGER_MDIS_Basemap_LOI_Mosaic_Global_166m.tif",
        filename="mercury_loi_166m_v1.tif",
        expected_bytes=4247471083,
        format="tiff",
        citation="MESS-H-MDIS-5-RDR-LOI-V1.0; USGS 8-bit global GeoTIFF distribution, 2016",
    ),
)


def sha256_file(path: Path) -> str:
    """Hash a file by streaming, without loading it into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_signature(data: bytes, kind: str) -> None:
    """Reject HTML challenges and incorrect source formats before saving."""
    if not data or b"<html" in data[:512].lower() or b"<!doctype" in data[:512].lower():
        raise ValueError("empty response or HTML page instead of source data")
    if kind == "tiff" and data[:4] not in (b"II*\x00", b"II+\x00", b"MM\x00*", b"MM\x00+"):
        raise ValueError("source is not a TIFF")
    if kind == "csv" and not data.startswith(b"id,lat_n,lon_e_0,"):
        raise ValueError("unexpected catalogue columns")


def acquire(source: SourceSpec, directory: Path) -> DownloadRecord:
    """Download once, validate and hash; preserve existing complete or partial files."""
    directory = directory.resolve()
    if "raw" in [part.lower() for part in directory.parts]:
        raise ValueError("acquisition must not write under data/raw")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / source.filename
    receipt = directory / f"{source.filename}.provenance.json"
    if target.exists() or receipt.exists():
        if not (target.is_file() and receipt.is_file()):
            raise FileExistsError("incomplete acquisition; use a new directory")
        record = DownloadRecord.model_validate_json(receipt.read_text(encoding="utf-8"))
        if record.source != source or record.bytes != target.stat().st_size:
            raise ValueError("source identity or file size mismatch")
        if record.sha256 != sha256_file(target):
            raise ValueError("existing source checksum mismatch")
        return record.model_copy(update={"path": str(target)})
    partial = directory / f"{source.filename}.part"
    if partial.exists():
        raise FileExistsError("partial download retained; use a new directory")
    request = Request(str(source.url), headers={"User-Agent": "Mozilla/5.0"})
    started = time.monotonic()
    with urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise ValueError(f"expected complete HTTP 200 response, got {response.status}")
        first = response.read(1024 * 1024)
        validate_signature(first, source.format)
        digest = hashlib.sha256()
        count = 0
        last_report = started
        with partial.open("xb") as stream:
            chunk = first
            while chunk:
                count += len(chunk)
                if count > source.expected_bytes:
                    raise ValueError("download exceeds pinned source size")
                stream.write(chunk)
                digest.update(chunk)
                if time.monotonic() - last_report >= 20:
                    print(
                        f"{source.source_id}: {count / 1e6:.0f}/"
                        f"{source.expected_bytes / 1e6:.0f} MB",
                        flush=True,
                    )
                    last_report = time.monotonic()
                chunk = response.read(1024 * 1024)
        if count != source.expected_bytes:
            raise ValueError(f"incomplete source: {count} != {source.expected_bytes}")
        record = DownloadRecord(
            source=source,
            retrieved_utc=datetime.now(UTC),
            path=str(target),
            bytes=count,
            sha256=digest.hexdigest(),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
    partial.rename(target)
    with receipt.open("x", encoding="utf-8") as stream:
        stream.write(record.model_dump_json(indent=2))
    print(f"{source.source_id}: verified {count} bytes, sha256={record.sha256}", flush=True)
    return record


def load_sources(directory: Path) -> list[DownloadRecord]:
    """Resolve copied receipts locally, check pinned identities, and verify complete files."""
    directory = directory.resolve()
    expected = {source.source_id: source for source in SOURCES}
    records: dict[str, DownloadRecord] = {}
    for receipt in sorted(directory.glob("*.provenance.json")):
        record = DownloadRecord.model_validate_json(receipt.read_text(encoding="utf-8"))
        source_id = record.source.source_id
        if source_id in records:
            raise ValueError(f"duplicate source receipt: {source_id}")
        if expected.get(source_id) != record.source:
            raise ValueError(f"unexpected source identity: {source_id}")
        target = (directory / record.source.filename).resolve()
        if target.parent != directory:
            raise ValueError("source file resolves outside the acquisition directory")
        if not target.is_file() or target.stat().st_size != record.bytes:
            raise ValueError(f"source missing or size mismatch: {source_id}")
        if sha256_file(target) != record.sha256:
            raise ValueError(f"source checksum mismatch: {source_id}")
        records[source_id] = record.model_copy(update={"path": str(target)})
    if records.keys() != expected.keys():
        raise ValueError("missing required source provenance")
    return list(records.values())


def main() -> None:
    """Acquire the pinned public products on explicit command invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda source: acquire(source, args.directory), SOURCES))


if __name__ == "__main__":
    main()
