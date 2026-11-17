"""Recycle bin service: listing, batch restore, and permanent deletion.

Soft-deleted items are visible here. Restoring reuses the existing
file/folder restore semantics. Purging is irreversible: file rows are
deleted and their blob refcounts decremented (blobs hit zero are removed
from disk as well). Folders are purged with their whole subtree.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import Settings
from ..models import ContentBlob, File, Folder
from ..storage import blob_store
from . import file_service, folder_service


def _deleted_folder_ids(db: SAMSession, user_id: str) -> list[str]:
    return list(
        db.execute(
            select(Folder.id).where(
                Folder.owner_id == user_id, Folder.deleted_at.is_not(None)
            )
        ).scalars()
    )


def list_trash(db: SAMSession, *, user_id: str) -> dict:
    """Top-level deleted items for the recycle bin screen."""
    deleted_folder_ids = _deleted_folder_ids(db, user_id)

    folders = (
        db.execute(
            select(Folder)
            .where(Folder.owner_id == user_id, Folder.deleted_at.is_not(None))
            .order_by(Folder.deleted_at.desc(), Folder.name.asc())
        )
        .scalars()
        .all()
    )

    files_stmt = (
        select(File)
        .where(File.owner_id == user_id, File.deleted_at.is_not(None))
        .order_by(File.deleted_at.desc(), File.name.asc())
    )
    if deleted_folder_ids:
        # Files inside a deleted folder belong to that folder's row.
        # NB: NOT IN excludes NULLs, so keep root-level files explicitly.
        files_stmt = files_stmt.where(
            or_(File.folder_id.is_(None), File.folder_id.not_in(deleted_folder_ids))
        )
    files = db.execute(files_stmt).scalars().all()

    # Storage math counts every soft-deleted file, including files inside
    # deleted folders (they are part of what the bin is holding).
    total_bytes = int(
        db.execute(
            select(func.coalesce(func.sum(File.size_bytes), 0)).where(
                File.owner_id == user_id, File.deleted_at.is_not(None)
            )
        ).scalar_one()
    )
    return {"files": files, "folders": folders, "total_bytes": total_bytes}


def _subtree_files(
    db: SAMSession, user_id: str, folders: list[Folder]
) -> list[File]:
    """Files inside the given deleted folders (counted for storage math)."""
    if not folders:
        return []
    all_ids: set[str] = set()
    for folder in folders:
        all_ids |= folder_service.subtree_ids(db, folder, include_deleted=True)
    if not all_ids:
        return []
    return list(
        db.execute(
            select(File).where(
                File.owner_id == user_id, File.folder_id.in_(all_ids)
            )
        ).scalars()
    )


def restore_items(
    db: SAMSession,
    *,
    user_id: str,
    file_ids: list[str],
    folder_ids: list[str],
) -> dict[str, int]:
    """Restore deleted files/folders by id (ownership-scoped, idempotent)."""
    counts = {"folders": 0, "files": 0}
    for folder_id in folder_ids:
        folder = folder_service.get_folder_owned(
            db, user_id=user_id, folder_id=folder_id, include_deleted=True
        )
        if folder.deleted_at is None:
            continue
        counts.update(folder_service.restore_folder(db, folder))
    for file_id in file_ids:
        row = file_service.get_file_owned(
            db, user_id=user_id, file_id=file_id, deleted=True
        )
        if row.deleted_at is None:
            continue
        if row.folder_id is not None:
            parent = db.get(Folder, row.folder_id)
            if parent is not None and parent.deleted_at is not None:
                # Part of a deleted folder: restore via the folder instead.
                raise HTTPException(
                    status.HTTP_409_CONFLICT, detail={"error": "inside_deleted_folder"}
                )
        file_service.restore_file(db, row)
        counts["files"] += 1
    return counts


def _delete_file_rows(db: SAMSession, settings: Settings, files: list[File]) -> int:
    """Delete file rows, decrement blob refcounts, drop empty blobs + bytes."""
    from ..models import FileVersion, Favorite, Upload

    freed = 0
    file_ids = [row.id for row in files]
    blob_shas = {row.blob_sha256 for row in files}
    if file_ids:
        db.query(FileVersion).filter(FileVersion.file_id.in_(file_ids)).delete(
            synchronize_session=False
        )
        db.query(Favorite).filter(Favorite.file_id.in_(file_ids)).delete(
            synchronize_session=False
        )
    for row in files:
        freed += row.size_bytes
        db.delete(row)
    db.flush()  # file rows must be gone before blobs can be dropped
    for sha in blob_shas:
        blob = db.get(ContentBlob, sha)
        if blob is None:
            continue
        blob.ref_count = max(0, blob.ref_count - len(
            [row for row in files if row.blob_sha256 == sha]
        ))
        if blob.ref_count <= 0:
            # Completed upload records also reference the blob; detach them
            # so the FK allows the row to go.
            db.query(Upload).filter(Upload.final_blob_sha256 == sha).update(
                {Upload.final_blob_sha256: None}, synchronize_session=False
            )
            blob_store.delete_blob_if_unref(settings, blob.sha256)
            db.delete(blob)
    return freed


def purge_items(
    db: SAMSession,
    settings: Settings,
    *,
    user_id: str,
    mode: str,
    file_ids: list[str],
    folder_ids: list[str],
) -> dict[str, int]:
    """Permanently delete selected items (or everything when mode == "all")."""
    if mode == "all":
        contents = list_trash(db, user_id=user_id)
        folders: list[Folder] = list(contents["folders"])
        files: list[File] = list(contents["files"])
        # Files under the deleted folders ride along with the folder purge.
        files = [f for f in files if f.folder_id is None or f.folder_id not in
                 {folder.id for folder in folders}]
        files += _subtree_files(db, user_id, folders)
    else:
        folders = []
        for folder_id in folder_ids:
            folder = folder_service.get_folder_owned(
                db, user_id=user_id, folder_id=folder_id, include_deleted=True
            )
            if folder.deleted_at is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, detail={"error": "folder_not_deleted"}
                )
            folders.append(folder)
        files = []
        for file_id in file_ids:
            row = file_service.get_file_owned(
                db, user_id=user_id, file_id=file_id, deleted=True
            )
            if row.deleted_at is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, detail={"error": "file_not_deleted"}
                )
            if row.folder_id is not None:
                parent = db.get(Folder, row.folder_id)
                if parent is not None and parent.deleted_at is not None:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        detail={"error": "inside_deleted_folder"},
                    )
            files.append(row)
        files += _subtree_files(db, user_id, folders)

    bytes_freed = _delete_file_rows(db, settings, files)
    folder_count = len(folders)
    file_count = len(files)
    for folder in folders:
        db.delete(folder)
    return {"files": file_count, "folders": folder_count, "bytes_freed": bytes_freed}


def trash_stats(db: SAMSession, *, user_id: str) -> dict:
    """Small counters for UI badges."""
    deleted_folder_ids = _deleted_folder_ids(db, user_id)
    folder_total = len(deleted_folder_ids)
    file_stmt = select(func.count()).select_from(File).where(
        File.owner_id == user_id, File.deleted_at.is_not(None)
    )
    if deleted_folder_ids:
        file_stmt = file_stmt.where(
            or_(File.folder_id.is_(None), File.folder_id.not_in(deleted_folder_ids))
        )
    file_total = db.execute(file_stmt).scalar_one()
    return {"files": int(file_total), "folders": int(folder_total)}
