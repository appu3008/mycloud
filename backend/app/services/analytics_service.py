"""Storage analytics service: usage vs quota, exact-duplicate detection.

Duplicates are exact because every file points at a content-addressed
blob (sha256): two files share a blob only when their bytes are identical.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import get_settings
from ..models import File, Folder
from . import upload_service


def storage_usage(db: SAMSession, *, user_id: str) -> dict:
    """Live usage, quota and counts for the monitor screen."""
    used = int(upload_service.active_usage_bytes(db, user_id))
    quota = upload_service._quota_bytes(db, get_settings(), user_id)
    file_count = int(
        db.execute(
            select(func.count()).select_from(File).where(
                File.owner_id == user_id, File.deleted_at.is_(None)
            )
        ).scalar_one()
    )
    folder_count = int(
        db.execute(
            select(func.count()).select_from(Folder).where(
                Folder.owner_id == user_id, Folder.deleted_at.is_(None)
            )
        ).scalar_one()
    )
    trash_files = int(
        db.execute(
            select(func.count()).select_from(File).where(
                File.owner_id == user_id, File.deleted_at.is_not(None)
            )
        ).scalar_one()
    )
    trash_bytes = int(
        db.execute(
            select(func.coalesce(func.sum(File.size_bytes), 0)).where(
                File.owner_id == user_id, File.deleted_at.is_not(None)
            )
        ).scalar_one()
    )
    return {
        "used_bytes": used,
        "quota_bytes": quota,
        "file_count": file_count,
        "folder_count": folder_count,
        "trash_files": trash_files,
        "trash_bytes": trash_bytes,
    }


def duplicate_groups(db: SAMSession, *, user_id: str) -> dict:
    """Group active files by their blob; only groups with 2+ copies matter."""
    rows = db.execute(
        select(File)
        .where(File.owner_id == user_id, File.deleted_at.is_(None))
        .order_by(File.name.asc())
    ).scalars().all()

    by_blob: dict[str, list[File]] = {}
    for row in rows:
        by_blob.setdefault(row.blob_sha256, []).append(row)

    groups = []
    total_wasted = 0
    for sha, copies in by_blob.items():
        if len(copies) < 2:
            continue
        size = copies[0].size_bytes
        wasted = size * (len(copies) - 1)
        total_wasted += wasted
        groups.append(
            {
                "sha256": sha,
                "size_bytes": size,
                "copies": len(copies),
                "wasted_bytes": wasted,
                "items": copies,
            }
        )
    groups.sort(key=lambda group: (-group["wasted_bytes"], group["sha256"]))
    return {
        "groups": groups,
        "group_count": len(groups),
        "total_wasted_bytes": total_wasted,
    }
