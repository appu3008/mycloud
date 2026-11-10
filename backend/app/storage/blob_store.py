"""Content-addressed blob storage (SHA-256 keying, refcounted ownership).

Layout (ARCHITECTURE.md): storage/files/aa/ab/<sha256hex>.blob
- The physical file exists iff a ContentBlob row with ref_count > 0 says so.
- put_temp_file() finalizes an assembled stream: hash-then-rename so either
  the blob exists complete or not at all (crash-safe ordering).
- Deduplication: an arriving blob whose hash already exists increments the
  refcount and the incoming bytes are discarded — never a silent overwrite.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

from ..core.config import Settings


class BlobIntegrityError(Exception):
    """Assembled bytes' SHA-256 did not match the expected digest."""


def blob_relpath(sha256_hex: str) -> str:
    """aa/ab/<hex>.blob path fragment relative to files_dir."""
    sha256_hex = sha256_hex.lower()
    if len(sha256_hex) != 64 or any(c not in "0123456789abcdef" for c in sha256_hex):
        raise ValueError("invalid sha256 hex")
    return os.path.join(sha256_hex[:2], sha256_hex[2:4], f"{sha256_hex}.blob")


def blob_abs_path(settings: Settings, sha256_hex: str) -> Path:
    return settings.files_dir / blob_relpath(sha256_hex)


def blob_exists(settings: Settings, sha256_hex: str) -> bool:
    return blob_abs_path(settings, sha256_hex).is_file()


def sha256_of_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def put_temp_file(
    settings: Settings, source_path: Path, expected_sha256: str | None
) -> str:
    """Move an assembled temp file into the blob store; return its hash.

    expected_sha256 (when provided) is verified BEFORE the move; a mismatch
    raises BlobIntegrityError and the temp file is left for caller cleanup.
    Deduplication: if the blob already exists, the oldest full copy wins and
    the temp bytes are simply discarded.
    """
    actual = sha256_of_file(source_path)
    if expected_sha256 and actual != expected_sha256:
        raise BlobIntegrityError(f"hash mismatch: {actual} != {expected_sha256}")

    destination = blob_abs_path(settings, actual)
    if destination.is_file():
        source_path.unlink(missing_ok=True)
        return actual

    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source_path, destination)
    os.chmod(destination, 0o640)
    return actual


def open_blob_stream(
    settings: Settings, sha256_hex: str, start: int = 0, end: int | None = None
) -> Iterator[bytes]:
    """Stream a blob (never whole-file buffering).

    Requests non-overlapping region [start, end) where end=None means EOF.
    Callers validate start/end bounds before invoking this.
    """
    path = blob_abs_path(settings, sha256_hex)
    if not path.is_file():
        raise FileNotFoundError(sha256_hex)
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = None if end is None else end - start
        while remaining != 0:
            block_size = 1024 * 512 if remaining is None else min(524288, remaining)
            block = handle.read(block_size)
            if not block:
                break
            if remaining is not None:
                remaining -= len(block)
            yield block


def delete_blob_if_unref(settings: Settings, sha256_hex: str) -> bool:
    """Remove physical bytes; safe even if absent; caller manages refcounts."""
    path = blob_abs_path(settings, sha256_hex)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
