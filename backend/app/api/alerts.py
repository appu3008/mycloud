"""Quota alerts API (v1): current status + notification dismissal."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SessionSAM

from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..services import alert_service
from .dependencies import csrf_protected_auth, get_current_auth

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def status(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> dict:
    user, _ = auth
    return alert_service.alert_status(db, user_id=user.id)


@router.post("/dismiss")
def dismiss(
    notification_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> dict:
    user, _ = auth
    found = alert_service.dismiss(db, user_id=user.id, notification_id=notification_id)
    if not found:
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "notification_not_found"})
    db.commit()
    return {"dismissed": notification_id}
