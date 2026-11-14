"""Folders API (v1): hierarchy CRUD, tree, recursive soft-delete/restore.

Route order matters: fixed paths (``/tree``, ``/batch``) are declared before
``/{folder_id}`` so they are never captured as ids.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as SAMSession

from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas.folders import (
    FolderBatch,
    FolderCreate,
    FolderDetail,
    FolderInfo,
    FolderMove,
    FolderRename,
)
from ..services import folder_service
from .dependencies import csrf_protected_auth, get_current_auth

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("")
def list_folders(
    parent_id: str | None = None,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    """Children of a folder (root when parent_id omitted), ownership-scoped."""
    user, _ = auth
    if parent_id is not None:
        folder_service.get_folder_owned(db, user_id=user.id, folder_id=parent_id)
    rows = folder_service.list_children(db, user_id=user.id, parent_id=parent_id)
    items = [FolderInfo.model_validate(row).model_dump(mode="json") for row in rows]
    return {"items": items, "total": len(items)}


@router.get("/tree")
def folder_tree(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> list[dict]:
    user, _ = auth
    return folder_service.folder_tree(db, user_id=user.id)


@router.post(
    "", response_model=FolderInfo, status_code=status.HTTP_201_CREATED
)
def create_folder(
    body: FolderCreate,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> FolderInfo:
    user, _ = auth
    folder = folder_service.create_folder(
        db, user_id=user.id, parent_id=body.parent_id, name=body.name
    )
    db.commit()
    return FolderInfo.model_validate(folder)


@router.get("/{folder_id}", response_model=FolderDetail)
def folder_detail(
    folder_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> FolderDetail:
    """Folder metadata plus root-to-folder breadcrumb for navigation."""
    user, _ = auth
    folder = folder_service.get_folder_owned(db, user_id=user.id, folder_id=folder_id)
    detail = FolderDetail.model_validate(folder)
    detail.breadcrumb = [
        FolderInfo.model_validate(row)
        for row in folder_service.breadcrumb(db, folder)
    ]
    return detail


@router.patch("/{folder_id}", response_model=FolderInfo)
def rename_folder(
    folder_id: str,
    body: FolderRename,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> FolderInfo:
    user, _ = auth
    folder = folder_service.get_folder_owned(db, user_id=user.id, folder_id=folder_id)
    folder_service.rename_folder(db, folder, new_name=body.name)
    db.commit()
    return FolderInfo.model_validate(folder)


@router.post("/{folder_id}/move", response_model=FolderInfo)
def move_folder(
    folder_id: str,
    body: FolderMove,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> FolderInfo:
    user, _ = auth
    folder = folder_service.get_folder_owned(db, user_id=user.id, folder_id=folder_id)
    folder_service.move_folder(db, folder, new_parent_id=body.parent_id)
    db.commit()
    return FolderInfo.model_validate(folder)


@router.delete("/{folder_id}")
def delete_folder(
    folder_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    """Recursive soft-delete; contents land in the recycle bin (phase 6 UI)."""
    user, _ = auth
    folder = folder_service.get_folder_owned(db, user_id=user.id, folder_id=folder_id)
    counts = folder_service.soft_delete_folder(db, folder)
    db.commit()
    return {"deleted": counts}


@router.post("/{folder_id}/restore")
def restore_folder(
    folder_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, _ = auth
    folder = folder_service.get_folder_owned(
        db, user_id=user.id, folder_id=folder_id, include_deleted=True
    )
    counts = folder_service.restore_folder(db, folder)
    db.commit()
    return {"restored": counts}


@router.post("/batch")
def batch_folders(
    body: FolderBatch,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    """Multi-select operations: delete / restore / move."""
    user, _ = auth
    unique_ids = list(dict.fromkeys(body.folder_ids))
    moved = deleted = restored = 0
    for folder_id in unique_ids:
        folder = folder_service.get_folder_owned(
            db, user_id=user.id, folder_id=folder_id,
            include_deleted=body.action == "restore",
        )
        if body.action == "delete":
            counts = folder_service.soft_delete_folder(db, folder)
            deleted += counts["folders"]
        elif body.action == "restore":
            counts = folder_service.restore_folder(db, folder)
            restored += counts["folders"]
        else:  # move
            folder_service.move_folder(db, folder, new_parent_id=body.parent_id)
            moved += 1
    key = {"delete": "deleted", "restore": "restored", "move": "moved"}[body.action]
    db.commit()
    return {key: {"folders": deleted + restored + moved}}
