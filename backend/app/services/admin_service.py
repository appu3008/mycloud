"""Administration service: cross-user overview, user controls, audit feed."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..models import (
    ActivityEvent,
    AuditLog,
    Backup,
    ContentBlob,
    Device,
    File,
    Folder,
    Session as SessionRow,
    Share,
    User,
)


def overview(db: SAMSession) -> dict:
    def scalar(stmt) -> int:
        return int(db.execute(stmt).scalar_one())

    live_files = select(func.count()).select_from(File).where(File.deleted_at.is_(None))
    live_bytes = select(func.coalesce(func.sum(File.size_bytes), 0)).where(
        File.deleted_at.is_(None)
    )
    return {
        "users": scalar(select(func.count()).select_from(User)),
        "active_users": scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        ),
        "admins": scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        ),
        "files": scalar(live_files),
        "bytes": scalar(live_bytes),
        "folders": scalar(
            select(func.count()).select_from(Folder).where(Folder.deleted_at.is_(None))
        ),
        "blobs": scalar(select(func.count()).select_from(ContentBlob)),
        "active_sessions": scalar(
            select(func.count()).select_from(SessionRow).where(
                SessionRow.revoked_at.is_(None)
            )
        ),
        "devices": scalar(select(func.count()).select_from(Device)),
        "shares": scalar(select(func.count()).select_from(Share)),
        "backups": scalar(select(func.count()).select_from(Backup)),
        "activity_events": scalar(select(func.count()).select_from(ActivityEvent)),
        "audit_events": scalar(select(func.count()).select_from(AuditLog)),
    }


def list_users(db: SAMSession) -> list[dict]:
    rows = db.execute(select(User).order_by(User.created_at.asc())).scalars().all()
    result = []
    for user in rows:
        count, size = db.execute(
            select(func.count(), func.coalesce(func.sum(File.size_bytes), 0)).where(
                File.owner_id == user.id, File.deleted_at.is_(None)
            )
        ).one()
        result.append(
            {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "is_admin": user.is_admin,
                "is_active": user.is_active,
                "file_count": int(count),
                "used_bytes": int(size),
                "created_at": user.created_at,
            }
        )
    return result


def update_user(
    db: SAMSession,
    *,
    actor: User,
    user_id: str,
    is_active: bool | None,
    is_admin: bool | None,
) -> dict:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "user_not_found"})
    if target.id == actor.id and (is_admin is False or is_active is False):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "cannot_change_own_admin_access"}
        )
    if is_active is not None:
        target.is_active = is_active
    if is_admin is not None:
        target.is_admin = is_admin
        target.role = "admin" if is_admin else "user"
    return {
        "id": target.id,
        "email": target.email,
        "display_name": target.display_name,
        "role": target.role,
        "is_admin": target.is_admin,
        "is_active": target.is_active,
    }


def audit_feed(db: SAMSession, *, limit: int) -> list[dict]:
    rows = db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(max(1, min(limit, 200)))
    ).scalars().all()
    return [
        {
            "id": row.id,
            "action": row.action,
            "actor_email": row.actor_email,
            "actor_ip": row.actor_ip,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "detail": row.detail,
            "created_at": row.created_at,
        }
        for row in rows
    ]
