"""Administration API (v1): overview, user controls and audit feed (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as SessionSAM

from ..core.database import get_db
from ..models import User
from ..services import activity_service, admin_service
from .dependencies import csrf_protected_user, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    is_admin: bool | None = None


@router.get("/overview")
def overview(
    _: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> dict:
    return admin_service.overview(db)


@router.get("/users")
def users(
    _: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> dict:
    return {"items": admin_service.list_users(db)}


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    body: UserUpdate,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> dict:
    require_admin(actor)
    result = admin_service.update_user(
        db,
        actor=actor,
        user_id=user_id,
        is_active=body.is_active,
        is_admin=body.is_admin,
    )
    from ..security.audit import record_audit

    record_audit(
        db,
        action="admin.user.updated",
        actor_user_id=actor.id,
        actor_email=actor.email,
        target_type="user",
        target_id=user_id,
        detail={"is_admin": result["is_admin"], "is_active": result["is_active"]},
    )
    activity_service.log_event(
        db, user_id=actor.id, kind="admin",
        summary=f"Updated user \u201c{result['email']}\u201d",
    )
    db.commit()
    return result


@router.get("/audit")
def audit(
    limit: int = 50,
    _: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> dict:
    return {"items": admin_service.audit_feed(db, limit=limit)}
