"""File version history: archive previous blobs, list and restore versions.

Uploading with ``replace_file_id`` archives the file's current blob as a
numbered version before the row is re-pointed at the new blob. Old blobs are
never deleted (they are still needed for restore and download), and each file
keeps at most ``MAX_VERSIONS`` archives; the oldest are pruned on write.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..models import ContentBlob, File, FileVersion, new_id, utcnow

MAX_VERSIONS = 20


def next_version_number(db: SAMSession, file_id: str) -> int:
    highest = db.execute(
        select(func.coalesce(func.max(FileVersion.version_number), 0)).where(
            FileVersion.file_id == file_id
        )
    ).scalar_one()
    return int(highest) + 1


def archive_current(
    db: SAMSession, file_row: File, *, created_by: str, new_sha256: str | None = None
) -> FileVersion | None:
    """Snapshot the file's current blob; returns None if there is nothing new."""
    if new_sha256 is not None and new_sha256 == file_row.blob_sha256:
        return None  # identical content: nothing to archive
    latest = db.execute(
        select(FileVersion.blob_sha256)
        .where(FileVersion.file_id == file_row.id)
        .order_by(FileVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest == file_row.blob_sha256:
        return None  # same content: no new version

    version = FileVersion(
        id=new_id(),
        file_id=file_row.id,
        version_number=next_version_number(db, file_row.id),
        blob_sha256=file_row.blob_sha256,
        size_bytes=file_row.size_bytes,
        created_by=created_by,
        created_at=utcnow(),
    )
    db.add(version)
    _prune(db, file_row.id)
    return version


def _prune(db: SAMSession, file_id: str) -> None:
    rows = db.execute(
        select(FileVersion)
        .where(FileVersion.file_id == file_id)
        .order_by(FileVersion.version_number.desc())
    ).scalars().all()
    for stale in rows[MAX_VERSIONS:]:
        db.delete(stale)


def list_versions(db: SAMSession, *, user_id: str, file_id: str) -> list[dict]:
    from .file_service import get_file_owned

    get_file_owned(db, user_id=user_id, file_id=file_id)
    rows = db.execute(
        select(FileVersion)
        .where(FileVersion.file_id == file_id)
        .order_by(FileVersion.version_number.desc())
    ).scalars().all()
    return [
        {
            "id": row.id,
            "version_number": row.version_number,
            "blob_sha256": row.blob_sha256,
            "size_bytes": row.size_bytes,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def owned_version(db: SAMSession, *, user_id: str, file_id: str, version_id: str) -> FileVersion:
    from .file_service import get_file_owned

    file_row = get_file_owned(db, user_id=user_id, file_id=file_id)
    version = db.get(FileVersion, version_id)
    if version is None or version.file_id != file_row.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "version_not_found"})
    return version


def restore_version(db: SAMSession, *, user_id: str, file_id: str, version_id: str) -> File:
    """Archive the current content, then re-point the file at the old blob."""
    from .file_service import get_file_owned

    file_row = get_file_owned(db, user_id=user_id, file_id=file_id)
    version = owned_version(db, user_id=user_id, file_id=file_id, version_id=version_id)
    archive_current(db, file_row, created_by="restore-before")
    target_sha = version.blob_sha256
    target = db.get(ContentBlob, target_sha)
    if target is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "blob_missing"})
    file_row.blob_sha256 = target.sha256
    file_row.size_bytes = target.size_bytes
    file_row.mtime = utcnow()
    # The version we just restored stays available as history; dropping it
    # keeps the timeline monotonic and avoids instantly re-archiving it.
    db.delete(version)
    return file_row
