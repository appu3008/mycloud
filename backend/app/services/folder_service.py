"""Folder service: hierarchy management, ownership-scoped.

Design notes
------------
- Paths are "/"-joined name chains (root folder ``Docs`` -> ``Docs``, nested
  -> ``Docs/Photos``). They are a convenience for breadcrumbs/tree rendering,
  always derived from the parent chain, never trusted as identity.
- Deletes are soft and recursive: the folder, its whole subtree, and every
  file inside are stamped with the *same* ``deleted_at`` timestamp. The
  recycle-bin phase restores exactly that timestamp batch, so a file the user
  deleted individually before the folder deletion stays in the bin.
- Moving/renaming rewrites descendant paths by walking the subtree through
  ``parent_id`` (never by LIKE-matching path strings, which breaks on names
  containing ``%``/``_`` or mixed case).
- Blobs are never touched here; soft-deleting only unhooks rows.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..models import File, Folder, utcnow
from . import file_service


def get_folder_owned(
    db: SAMSession,
    *,
    user_id: str,
    folder_id: str,
    include_deleted: bool = False,
) -> Folder:
    stmt = select(Folder).where(Folder.id == folder_id, Folder.owner_id == user_id)
    if not include_deleted:
        stmt = stmt.where(Folder.deleted_at.is_(None))
    folder = db.execute(stmt).scalar_one_or_none()
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "folder_not_found"})
    return folder


def breadcrumb(db: SAMSession, folder: Folder) -> list[Folder]:
    """Ancestor chain from the root-most folder down to ``folder`` itself."""
    chain: list[Folder] = []
    current: Folder | None = folder
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(current)
        if current.parent_id is None:
            break
        current = db.get(Folder, current.parent_id)
    chain.reverse()
    return chain


def _name_conflict(db: SAMSession, *, user_id: str, parent_id: str | None, name: str) -> bool:
    stmt = select(Folder.id).where(
        Folder.owner_id == user_id,
        Folder.deleted_at.is_(None),
        Folder.name == name,
    )
    stmt = stmt.where(
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def _conflict() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT, detail={"error": "folder_name_conflict"}
    )


def create_folder(
    db: SAMSession, *, user_id: str, parent_id: str | None, name: str
) -> Folder:
    parent = None
    if parent_id is not None:
        parent = get_folder_owned(db, user_id=user_id, folder_id=parent_id)
    if _name_conflict(db, user_id=user_id, parent_id=parent_id, name=name):
        raise _conflict()
    folder = Folder(
        owner_id=user_id,
        parent_id=parent_id,
        name=name,
        path=join_path(parent, name),
    )
    db.add(folder)
    db.flush()
    return folder


def join_path(parent: Folder | None, name: str) -> str:
    return f"{parent.path}/{name}" if parent is not None else name


def list_children(
    db: SAMSession, *, user_id: str, parent_id: str | None
) -> list[Folder]:
    stmt = select(Folder).where(
        Folder.owner_id == user_id, Folder.deleted_at.is_(None)
    )
    stmt = stmt.where(
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
    )
    return list(db.execute(stmt.order_by(Folder.name)).scalars().all())


def subtree_ids(db: SAMSession, root: Folder, *, include_deleted: bool = False) -> set[str]:
    """All ids in the subtree (root included).

    Non-deleted only by default; restore passes ``include_deleted=True`` to
    see through the cascade it is undoing.
    """
    ids = {root.id}
    frontier = [root.id]
    while frontier:
        stmt = select(Folder.id).where(Folder.parent_id.in_(frontier))
        if not include_deleted:
            stmt = stmt.where(Folder.deleted_at.is_(None))
        children = db.execute(stmt).scalars().all()
        children = [cid for cid in children if cid not in ids]
        ids.update(children)
        frontier = children
    return ids


def _rewrite_subtree_paths(db: SAMSession, folder: Folder) -> None:
    """Recompute ``path`` for ``folder`` and every non-deleted descendant."""
    folder.path = (
        join_path(db.get(Folder, folder.parent_id), folder.name)
        if folder.parent_id is not None
        else folder.name
    )
    paths = {folder.id: folder.path}
    frontier = [folder.id]
    while frontier:
        children = db.execute(
            select(Folder).where(
                Folder.parent_id.in_(frontier), Folder.deleted_at.is_(None)
            )
        ).scalars().all()
        for child in children:
            child.path = f"{paths[child.parent_id]}/{child.name}"
            paths[child.id] = child.path
        frontier = [child.id for child in children]


def rename_folder(db: SAMSession, folder: Folder, *, new_name: str) -> Folder:
    if new_name != folder.name:
        if _name_conflict(
            db, user_id=folder.owner_id, parent_id=folder.parent_id, name=new_name
        ):
            raise _conflict()
        folder.name = new_name
        _rewrite_subtree_paths(db, folder)
        folder.updated_at = utcnow()
    return folder


def _assert_not_descendant(db: SAMSession, folder: Folder, new_parent_id: str) -> None:
    """Moving a folder into itself or its subtree would create a cycle."""
    current_id: str | None = new_parent_id
    seen: set[str] = set()
    while current_id is not None and current_id not in seen:
        if current_id == folder.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail={"error": "folder_cycle"}
            )
        seen.add(current_id)
        parent = db.get(Folder, current_id)
        current_id = parent.parent_id if parent is not None else None


def move_folder(
    db: SAMSession, folder: Folder, *, new_parent_id: str | None
) -> Folder:
    if new_parent_id == folder.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "folder_cycle"})
    if new_parent_id == folder.parent_id:
        return folder  # no-op move
    if new_parent_id is not None:
        get_folder_owned(db, user_id=folder.owner_id, folder_id=new_parent_id)
        _assert_not_descendant(db, folder, new_parent_id)
    if _name_conflict(
        db, user_id=folder.owner_id, parent_id=new_parent_id, name=folder.name
    ):
        raise _conflict()
    folder.parent_id = new_parent_id
    _rewrite_subtree_paths(db, folder)
    folder.updated_at = utcnow()
    return folder


def soft_delete_folder(db: SAMSession, folder: Folder) -> dict[str, int]:
    """Soft-delete the folder, its subtree, and all contained files.

    Everything deleted in this cascade shares one ``deleted_at`` value so the
    recycle bin can restore the batch as a unit.
    """
    now = utcnow()
    ids = subtree_ids(db, folder)
    folders = db.execute(
        select(Folder).where(Folder.id.in_(ids), Folder.deleted_at.is_(None))
    ).scalars().all()
    for row in folders:
        row.deleted_at = now
    files = db.execute(
        select(File).where(
            File.folder_id.in_(ids), File.owner_id == folder.owner_id,
            File.deleted_at.is_(None),
        )
    ).scalars().all()
    for row in files:
        row.deleted_at = now
    return {"folders": len(folders), "files": len(files)}


def restore_folder(db: SAMSession, folder: Folder) -> dict[str, int]:
    """Undo a cascade delete: restore exactly the batch stamped at the same
    ``deleted_at`` timestamp (files deleted individually stay deleted)."""
    batch_ts = folder.deleted_at
    if batch_ts is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "folder_not_deleted"}
        )
    ids = subtree_ids(db, folder, include_deleted=True)
    folders = db.execute(
        select(Folder).where(Folder.id.in_(ids), Folder.deleted_at == batch_ts)
    ).scalars().all()
    for row in folders:
        row.deleted_at = None
    files = db.execute(
        select(File).where(
            File.folder_id.in_(ids), File.owner_id == folder.owner_id,
            File.deleted_at == batch_ts,
        )
    ).scalars().all()
    for row in files:
        row.deleted_at = None
    # Paths may be stale if ancestors moved while items were deleted; rebuild.
    _rewrite_subtree_paths(db, folder)
    return {"folders": len(folders), "files": len(files)}


def folder_tree(db: SAMSession, *, user_id: str) -> list[dict]:
    """Full non-deleted hierarchy as a nested structure for the sidebar."""
    rows = db.execute(
        select(Folder)
        .where(Folder.owner_id == user_id, Folder.deleted_at.is_(None))
        .order_by(Folder.name)
    ).scalars().all()
    nodes: dict[str, dict] = {}
    roots: list[dict] = []
    for row in rows:
        nodes[row.id] = {
            "id": row.id,
            "name": row.name,
            "path": row.path,
            "children": [],
        }
    for row in rows:
        node = nodes[row.id]
        if row.parent_id is not None and row.parent_id in nodes:
            nodes[row.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def unique_copy_name(db: SAMSession, *, user_id: str, folder_id: str | None, name: str) -> str:
    """First free ``name (copy)``, ``name (copy 2)``… within the target folder."""
    stem, dot, ext = name.rpartition(".")
    base, suffix = (stem, f"{dot}{ext}") if stem and dot else (name, "")
    candidate = f"{base} (copy){suffix}"
    counter = 2
    taken = {
        row.name
        for row in db.execute(
            select(File).where(
                File.owner_id == user_id,
                File.deleted_at.is_(None),
                File.folder_id.is_(None) if folder_id is None else File.folder_id == folder_id,
            )
        ).scalars()
    }
    while candidate in taken:
        candidate = f"{base} (copy {counter}){suffix}"
        counter += 1
    return candidate


def assert_within_quota(db: SAMSession, settings, user_id: str, incoming_bytes: int) -> None:
    """Shared guard for copy-size changes (mirrors upload quota math)."""
    from ..services.upload_service import UploadRejected, _quota_bytes, active_usage_bytes

    projected = active_usage_bytes(db, user_id) + incoming_bytes
    if projected > _quota_bytes(db, settings, user_id):
        raise UploadRejected("quota_exceeded", f"projected {projected} bytes")


def owned_files_by_id(db: SAMSession, user_id: str, file_ids: list[str]) -> dict[str, File]:
    """Batch ownership lookup; missing ids are simply absent (caller 404s)."""
    rows = db.execute(
        select(File).where(File.id.in_(file_ids), File.owner_id == user_id)
    ).scalars().all()
    return {row.id: row for row in rows}


def ensure_folder_usable(db: SAMSession, *, user_id: str, folder_id: str | None) -> None:
    """404 unless the target folder is owned and active (moves/copies)."""
    file_service.folder_owned(db, user_id=user_id, folder_id=folder_id)
