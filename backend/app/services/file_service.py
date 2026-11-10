"""File service: ownership-scoped queries, download ranges, metadata.

Every query filters by owner_id from the authenticated session (IDOR guard).
Range math follows RFC 9110: suffix ranges (bytes=-N) and open ranges.
Concurrency of file rows deduplicated against content_blobs.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..models import File, Folder, User, utcnow


def get_file_owned(db: SAMSession, *, user_id: str, file_id: str, deleted: bool = False) -> File:
    row = db.execute(
        select(File).where(
            File.id == file_id,
            File.owner_id == user_id,
            File.deleted_at.is_(None) if not deleted else File.deleted_at.is_not(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "file_not_found"})
    return row


def list_folder_files(
    db: SAMSession,
    *,
    user_id: str,
    folder_id: str | None,
    limit: int,
    offset: int,
    sort: str = "name",
    order: str = "asc",
) -> tuple[list[File], int]:
    stmt = select(File).where(File.owner_id == user_id, File.deleted_at.is_(None))
    count_stmt = (
        select(func.count())
        .select_from(File)
        .where(File.owner_id == user_id, File.deleted_at.is_(None))
    )
    if folder_id is None:
        stmt = stmt.where(File.folder_id.is_(None))
        count_stmt = count_stmt.where(File.folder_id.is_(None))
    else:
        #ordinarily the folder itself is ownership-checked by the caller:
        stmt = stmt.where(File.folder_id == folder_id)
        count_stmt = count_stmt.where(File.folder_id == folder_id)

    sort_column = {
        "name": File.name,
        "size": File.size_bytes,
        "mtime": File.mtime,
        "uploaded": File.created_at,
    }.get(sort, File.name)
    direction = sort_column.asc() if order != "desc" else sort_column.desc()
    stmt = stmt.order_by(direction).limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    total = int(db.execute(count_stmt).scalar_one())
    return list(rows), total


def soft_delete_file(db: SAMSession, file_row: File) -> None:
    file_row.deleted_at = utcnow()


def restore_file(db: SAMSession, file_row: File) -> None:
    file_row.deleted_at = None


# ---------------------------------------------------------------------------
# Range parsing (RFC 9110), hardened: single range only, in-bounds enforced
# ---------------------------------------------------------------------------

def parse_range_header(value: str | None, size: int) -> tuple[int, int | None] | None:
    """Return (start, end_inclusive_or_None) or None (no/invalid header)."""
    if not value or not value.startswith("bytes="):
        return None
    spec = value[len("bytes="):]
    if "," in spec or "-" not in spec:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail={"error": "unsupported_range"},
        )
    start_text, end_text = spec.split("-", 1)
    if start_text == "":
        if not end_text.isdigit():
            raise HTTPException(
                status.HTTP_416_RANGE_NOT_SATISFIABLE,
                detail={"error": "unsupported_range"},
            )
        n = int(end_text)
        start = max(0, size - n)
        return start, None if n else size - 1  # bytes=-0 invalid per RFC
    if not start_text.isdigit():
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail={"error": "unsupported_range"},
        )
    start = int(start_text)
    if start >= size > 0:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail={"error": "range_not_satisfiable"},
        )
    if size == 0:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail={"error": "range_not_satisfiable"},
        )
    end = int(end_text) if end_text.isdigit() and int(end_text) < size else None
    return start, end


def stream_download(
    db: SAMSession, file_row: File, *, open_stream: Iterator[bytes]
) -> Iterator[bytes]:
    # Hook for future audit/activity emission (phase 12 instrumentation).
    yield from open_stream


def folder_owned(db: SAMSession, *, user_id: str, folder_id: str | None) -> Folder | None:
    if folder_id is None:
        return None
    folder = db.execute(
        select(Folder).where(Folder.id == folder_id, Folder.owner_id == user_id)
    ).scalar_one_or_none()
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "folder_not_found"})
    return folder


def current_quota_usage(db: SAMSession, user: User) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(File.size_bytes), 0)).where(
            File.owner_id == user.id, File.deleted_at.is_(None)
        )
    ).scalar_one()
    return int(total)
