"""Recycle bin API (v1): list deleted items, restore, permanent delete.

The bin shows top-level deleted items only — files inside a deleted folder
restore/purge through the folder itself, which keeps the cascade batch
semantics from phase 5 intact.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SAMSession

from ..core.config import get_settings
from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas.trash import (
    TrashContents,
    TrashCounts,
    TrashPurge,
    TrashRestore,
)
from ..services import activity_service, trash_service
from .dependencies import csrf_protected_auth, get_current_auth

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get("", response_model=TrashContents)
def trash_contents(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> TrashContents:
    """Everything currently sitting in the recycle bin."""
    user, _ = auth
    contents = trash_service.list_trash(db, user_id=user.id)
    return TrashContents(
        files=contents["files"],
        folders=contents["folders"],
        total_bytes=contents["total_bytes"],
    )


@router.get("/stats")
def trash_stats(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, _ = auth
    return trash_service.trash_stats(db, user_id=user.id)


@router.post("/restore")
def restore(
    body: TrashRestore,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    """Batch-restore deleted items back to their original locations."""
    user, _ = auth
    counts = trash_service.restore_items(
        db,
        user_id=user.id,
        file_ids=body.file_ids,
        folder_ids=body.folder_ids,
    )
    if counts["files"] or counts["folders"]:
        activity_service.log_event(
            db, user_id=user.id, kind="restore",
            summary=f"Restored {counts['files']} file(s), {counts['folders']} folder(s) from the bin",
        )
    db.commit()
    return {"restored": counts}


@router.post("/purge")
def purge(
    body: TrashPurge,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    """Permanently delete items (irreversible: blob refcounts are released)."""
    user, _ = auth
    counts = trash_service.purge_items(
        db,
        get_settings(),
        user_id=user.id,
        mode=body.mode,
        file_ids=body.file_ids,
        folder_ids=body.folder_ids,
    )
    if counts["files"] or counts["folders"]:
        activity_service.log_event(
            db, user_id=user.id, kind="delete",
            summary=f"Permanently deleted {counts['files']} file(s), {counts['folders']} folder(s)"
                    + (f" ({counts['bytes_freed'] // 1024} KiB freed)" if counts["bytes_freed"] else ""),
        )
    db.commit()
    return {"purged": counts}
