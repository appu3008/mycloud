"""Chunked, resumable upload orchestration (spec section 5).

Flow: reserve (quota + guardrails) -> chunk PUTs (per-chunk SHA-256,
idempotent re-PUT of same chunk) -> complete (stream final SHA-256 while
assembling, deduplicate via ContentBlob refcount, then create File).
Never loads whole files into RAM: chunk writes and final assembly stream.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import shutil
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import Settings
from ..models import ContentBlob, File, Folder, Upload, UploadChunk, User, new_id, utcnow
from ..storage import blob_store, disk
from ..storage.mime import extension_of, sanitize_filename, sniff_mime

_CHUNK_HASH_HEADER = "x-chunk-sha256"

_STATE_FAIL_CODES = {
    "quota": "quota_exceeded",
    "disk": "disk_protected",
    "size": "file_too_large",
}


class UploadRejected(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Quota math
# ---------------------------------------------------------------------------

def active_usage_bytes(db: SAMSession, user_id: str, *, exclude_upload_id: str | None = None) -> int:
    """Space used by active (non-deleted) files plus pending upload
    reservations (self-count avoidable at completion time)."""
    total = db.execute(
        select(func.coalesce(func.sum(File.size_bytes), 0)).where(
            File.owner_id == user_id, File.deleted_at.is_(None)
        )
    ).scalar_one()
    pending_stmt = select(func.coalesce(func.sum(Upload.size_bytes), 0)).where(
        Upload.user_id == user_id,
        Upload.state.in_(("reserved", "uploading", "assembling")),
    )
    if exclude_upload_id:
        pending_stmt = pending_stmt.where(Upload.id != exclude_upload_id)
    pending = db.execute(pending_stmt).scalar_one()
    return int(total) + int(pending)


def _quota_bytes(db: SAMSession, settings: Settings, user_id: str) -> int:
    return settings.default_quota_mb * 1024 * 1024


def _assert_quota(
    db: SAMSession,
    settings: Settings,
    *,
    user_id: str,
    incoming_bytes: int,
    exclude_upload_id: str | None = None,
) -> None:
    projected = active_usage_bytes(db, user_id, exclude_upload_id=exclude_upload_id) + incoming_bytes
    if projected > _quota_bytes(db, settings, user_id):
        raise UploadRejected("quota_exceeded", f"projected {projected} bytes")


def _assert_disk(settings: Settings, needed_bytes: int) -> None:
    allowance = disk.check_write_allowed(settings, needed_bytes)
    if not allowance.ok:
        raise UploadRejected("disk_protected", allowance.reason)


# ---------------------------------------------------------------------------
# Reserve / chunk / complete / abort
# ---------------------------------------------------------------------------

def reserve(
    db: SAMSession,
    settings: Settings,
    *,
    user: User,
    filename: str,
    size_bytes: int,
    target_folder_id: str | None,
    chunk_size_mb: int | None = None,
) -> tuple[Upload, str]:
    """Create the reservation. Returns (upload_row, public_upload_id)."""
    if size_bytes <= 0:
        raise UploadRejected("invalid_size")
    if size_bytes > settings.max_file_size_mb * 1024 * 1024:
        raise UploadRejected("file_too_large", f"limit {settings.max_file_size_mb} MB")
    filename = sanitize_filename(filename)
    _assert_quota(db, settings, user_id=user.id, incoming_bytes=size_bytes)
    _assert_disk(settings, size_bytes)

    if target_folder_id is not None:
        folder = db.execute(
            select(Folder).where(Folder.id == target_folder_id, Folder.owner_id == user.id)
        ).scalar_one_or_none()
        if folder is None:
            raise UploadRejected("folder_not_found")

    chunk_size = (chunk_size_mb or settings.upload_chunk_size_mb) * 1024 * 1024
    chunk_size = max(1, min(chunk_size, size_bytes))
    total_chunks = (size_bytes + chunk_size - 1) // chunk_size

    public_id = f"up_{secrets.token_hex(16)}"
    row = Upload(
        id=new_id(),
        user_id=user.id,
        target_folder_id=target_folder_id,
        filename=filename,
        size_bytes=size_bytes,
        chunk_size_bytes=chunk_size,
        total_chunks=total_chunks,
        received_chunks=0,
        state="reserved",
        client_upload_id=public_id,
        expires_at=utcnow() + timedelta(hours=24),
    )
    db.add(row)
    upload_temp_dir(settings, public_id).mkdir(parents=True, exist_ok=True)
    return row, public_id


def upload_temp_dir(settings: Settings, public_id: str) -> Path:
    return settings.temporary_dir / public_id


def chunk_path(settings: Settings, upload: Upload, chunk_number: int) -> Path:
    _validate_chunk_number(upload, chunk_number)
    return upload_temp_dir(settings, upload.client_upload_id) / f"{chunk_number:06d}.part"


def accept_chunk(
    db: SAMSession,
    settings: Settings,
    *,
    upload: Upload,
    chunk_number: int,
    body: bytes | Path,
    body_sha256: str,
) -> UploadChunk:
    """Validate + persist one chunk. Idempotent for identical re-sends.

    - chunk number must be in range
    - declared sha256 must match actual content (constant-time compare)
    - re-sending an already-saved chunk with the same hash is accepted
    """
    _assert_disk(settings, _size_hint(body))
    _validate_chunk_number(upload, chunk_number)
    if len(body_sha256) != 64:
        raise UploadRejected("invalid_chunk_hash")

    dest = chunk_path(settings, upload, chunk_number)
    existing = db.get(UploadChunk, (upload.id, chunk_number))
    if existing is not None:
        if hmac.compare_digest(existing.sha256, body_sha256):
            return existing
        raise UploadRejected("chunk_conflict", "same chunk already differs in content")

    hasher = hashlib.sha256()
    written = 0
    with dest.open("wb") as handle:
        for block in _iterate_bodies(body):
            hasher.update(block)
            handle.write(block)
            written += len(block)
    actual_hash = hasher.hexdigest()
    if not hmac.compare_digest(actual_hash, body_sha256):
        dest.unlink(missing_ok=True)
        raise UploadRejected("chunk_hash_mismatch", f"body hashed {actual_hash}")

    expected_size = upload.chunk_size_bytes
    if chunk_number == upload.total_chunks:
        expected_size = upload.size_bytes - upload.chunk_size_bytes * (upload.total_chunks - 1)
    if written != expected_size:
        dest.unlink(missing_ok=True)
        raise UploadRejected(
            "chunk_size_mismatch", f"got {written} bytes, expected {expected_size}"
        )

    row = UploadChunk(
        upload_id=upload.id,
        chunk_number=chunk_number,
        sha256=body_sha256,
        size_bytes=written,
        storage_path=str(dest),
        saved_at=utcnow(),
    )
    db.add(row)
    upload.received_chunks += 1
    if upload.state in ("reserved",):
        upload.state = "uploading"
    return row


def complete(
    db: SAMSession,
    settings: Settings,
    *,
    upload: Upload,
    filename_override: str | None = None,
    replace_file_id: str | None = None,
) -> File:
    """Assemble -> (apply final quota/disk checks) -> blob -> File row.

    Deduplication: if the assembled hash exists in content_blobs, the temp
    assembly is discarded and the existing blob gains a reference. The
    physical object never changes.
    """
    if upload.state in ("complete", "assembling", "aborted", "failed"):
        raise UploadRejected("invalid_state", f"state={upload.state}")
    if upload.received_chunks < upload.total_chunks:
        raise UploadRejected("missing_chunks", f"have {upload.received_chunks}")

    upload.state = "assembling"
    db.flush()

    work_dir = upload_temp_dir(settings, upload.client_upload_id)
    assembly_path = work_dir / "assembled.bin"

    hasher = hashlib.sha256()
    written = 0
    with assembly_path.open("wb") as out:
        for chunk in sorted(
            db.execute(
                select(UploadChunk).where(UploadChunk.upload_id == upload.id)
            ).scalars(),
            key=lambda c: c.chunk_number,
        ):
            for block in blob_stream_from(chunk.storage_path):
                hasher.update(block)
                out.write(block)
                written += len(block)
    if written != upload.size_bytes:
        raise UploadRejected("assembly_size_mismatch", f"wrote {written}")

    if written > settings.max_file_size_mb * 1024 * 1024:
        raise UploadRejected("file_too_large")

    # Replacing a file frees its old bytes from live usage, so only the
    # difference counts against quota (negative when the new file is smaller).
    replacing = None
    if replace_file_id:
        from .file_service import get_file_owned

        replacing = get_file_owned(db, user_id=upload.user_id, file_id=replace_file_id)
    incoming = written - (replacing.size_bytes if replacing else 0)
    _assert_quota(
        db,
        settings,
        user_id=upload.user_id,
        incoming_bytes=incoming,
        exclude_upload_id=upload.id,
    )
    if incoming > 0:
        _assert_disk(settings, incoming)

    sha256_hex = hasher.hexdigest()
    try:
        blob_store.put_temp_file(settings, assembly_path, sha256_hex)
    except blob_store.BlobIntegrityError as exc:
        raise UploadRejected("integrity_error", str(exc)) from exc

    blob = db.get(ContentBlob, sha256_hex)
    if blob is None:
        blob = ContentBlob(
            sha256=sha256_hex,
            size_bytes=written,
            ref_count=0,
            storage_path=blob_store.blob_relpath(sha256_hex),
            created_at=utcnow(),
        )
        db.add(blob)
        db.flush()  # referenced below by the File row (no ORM relationship)
    blob.ref_count += 1

    name = sanitize_filename(filename_override or upload.filename)
    mime_type = sniff_mime(_head_of(settings, sha256_hex))
    if replacing is not None:
        from . import version_service

        version_service.archive_current(
            db, replacing, created_by="upload-replace", new_sha256=sha256_hex
        )
        replacing.name = name
        replacing.extension = extension_of(name)
        replacing.mime_type = mime_type
        replacing.size_bytes = written
        replacing.blob_sha256 = sha256_hex
        replacing.mtime = utcnow()
        file_row = replacing
    else:
        file_row = File(
            id=new_id(),
            owner_id=upload.user_id,
            folder_id=upload.target_folder_id,
            name=name,
            extension=extension_of(name),
            mime_type=mime_type,
            size_bytes=written,
            blob_sha256=sha256_hex,
            mtime=utcnow(),
        )
        db.add(file_row)
    upload.state = "complete"
    upload.final_blob_sha256 = sha256_hex
    upload.final_file_id = file_row.id

    shutil.rmtree(work_dir, ignore_errors=True)
    return file_row


def abort(db: SAMSession, settings: Settings, *, upload: Upload) -> None:
    shutil.rmtree(upload_temp_dir(settings, upload.client_upload_id), ignore_errors=True)
    upload.state = "aborted"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _validate_chunk_number(upload: Upload, chunk_number: int) -> None:
    if chunk_number < 1 or chunk_number > upload.total_chunks:
        raise UploadRejected("chunk_out_of_range")


def _size_hint(body: bytes | Path) -> int:
    if isinstance(body, bytes):
        return len(body)
    return body.stat().st_size


def _iterate_bodies(body: bytes | Path):
    if isinstance(body, bytes):
        yield body
        return
    with body.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            yield block


def blob_stream_from(path: str):
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 512):
            yield block


def _head_of(settings: Settings, sha256_hex: str) -> bytes:
    try:
        path = blob_store.blob_abs_path(settings, sha256_hex)
        with path.open("rb") as handle:
            return handle.read(64)
    except OSError:
        return b""
