"""Offline acquisition validation; all response bytes are synthetic fixtures."""

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import ValidationError

from autonomous_modality.acquisition import (
    DownloadRecord,
    SourceSpec,
    acquire,
    load_sources,
    sha256_file,
    validate_signature,
)


class FakeResponse(BytesIO):
    """A local test response; no network access or observed data."""

    status = 200
    headers: ClassVar[dict[str, str]] = {"ETag": "fixture-etag"}


def test_download_is_create_only_and_detects_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"Synthetic source documentation, not scientific data."
    spec = SourceSpec(
        source_id="fixture",
        url="https://example.org/fixture.txt",
        filename="fixture.txt",
        expected_bytes=len(content),
        format="text",
        citation="Synthetic test fixture",
    )
    monkeypatch.setattr(
        "autonomous_modality.acquisition.urlopen", lambda *a, **kw: FakeResponse(content)
    )
    record = acquire(spec, tmp_path)
    assert record.bytes == len(content)
    assert record.sha256 == sha256_file(tmp_path / "fixture.txt")
    assert (
        DownloadRecord.model_validate_json((tmp_path / "fixture.txt.provenance.json").read_text())
        == record
    )

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("existing data must not be downloaded again")

    monkeypatch.setattr("autonomous_modality.acquisition.urlopen", no_network)
    assert acquire(spec, tmp_path) == record
    (tmp_path / "fixture.txt").write_bytes(b"x" * len(content))
    with pytest.raises(ValueError, match="checksum"):
        acquire(spec, tmp_path)


@pytest.mark.parametrize("content", [b"<html>challenge</html>", b"", b"IIxx"])
def test_reject_non_tiff_responses(content: bytes) -> None:
    with pytest.raises(ValueError):
        validate_signature(content, "tiff")


@pytest.mark.parametrize(
    "filename", ["../escape.csv", "nested/file.csv", "C:\\escape.csv", ".", "..", "file."]
)
def test_reject_source_path_traversal(filename: str) -> None:
    with pytest.raises(ValidationError):
        SourceSpec(
            source_id="fixture",
            url="https://example.org/fixture",
            filename=filename,
            expected_bytes=1,
            format="csv",
            citation="Synthetic fixture",
        )


def test_incomplete_download_is_not_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = SourceSpec(
        source_id="fixture",
        url="https://example.org/fixture.txt",
        filename="fixture.txt",
        expected_bytes=100,
        format="text",
        citation="Fixture",
    )
    monkeypatch.setattr(
        "autonomous_modality.acquisition.urlopen", lambda *a, **kw: FakeResponse(b"short")
    )
    with pytest.raises(ValueError, match="incomplete"):
        acquire(spec, tmp_path)
    assert not (tmp_path / "fixture.txt").exists()
    assert not (tmp_path / "fixture.txt.provenance.json").exists()
    assert (tmp_path / "fixture.txt.part").read_bytes() == b"short"
    with pytest.raises(FileExistsError):
        acquire(spec, tmp_path)
    with pytest.raises(ValueError, match="raw"):
        acquire(spec, tmp_path / "data" / "raw")


def test_receipt_does_not_accept_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DownloadRecord.model_validate({"invented": True, "retrieved_utc": datetime.now(UTC)})


@pytest.mark.parametrize("fault", [None, "duplicate", "identity", "checksum", "missing", "size"])
def test_source_loading_checks_local_files_and_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str | None,
) -> None:
    path = tmp_path / "fixture.txt"
    path.write_text("synthetic fixture", encoding="utf-8")
    spec = SourceSpec(
        source_id="fixture",
        url="https://example.org/fixture.txt",
        filename=path.name,
        expected_bytes=path.stat().st_size,
        format="text",
        citation="Synthetic fixture",
    )
    monkeypatch.setattr("autonomous_modality.acquisition.SOURCES", (spec,))
    record = DownloadRecord(
        source=spec,
        retrieved_utc=datetime.now(UTC),
        path="old-machine/fixture.txt",
        bytes=path.stat().st_size,
        sha256=sha256_file(path),
    )
    payload = record.model_dump(mode="json")
    if fault == "identity":
        payload["source"]["url"] = "https://example.org/different"
    if fault == "size":
        payload["bytes"] += 1
    receipt = tmp_path / "fixture.txt.provenance.json"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    original = receipt.read_bytes()
    if fault == "duplicate":
        (tmp_path / "duplicate.provenance.json").write_bytes(original)
    if fault == "checksum":
        path.write_bytes(b"x" * record.bytes)
    if fault == "missing":
        monkeypatch.setattr(
            "autonomous_modality.acquisition.SOURCES",
            (spec, spec.model_copy(update={"source_id": "other"})),
        )
    if fault:
        with pytest.raises(ValueError):
            load_sources(tmp_path)
    else:
        restored = load_sources(tmp_path)
        assert len(restored) == 1
        assert restored[0].path == str(path.resolve())
        assert acquire(spec, tmp_path).path == str(path.resolve())
        assert receipt.read_bytes() == original
