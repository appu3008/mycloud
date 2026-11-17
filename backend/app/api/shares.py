"""Share links API (v1): create/list/revoke links for files and folders."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SAMSession

from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas.shares import (
    ShareCreate,
    ShareCreated,
    ShareInfo,
    ShareList,
)
from ..services import share_service
from .dependencies import csrf_protected_auth, get_current_auth

router = APIRouter(prefix="/shares", tags=["shares"])


@router.post("", response_model=ShareCreated, status_code=201)
def create_share(
    body: ShareCreate,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> ShareCreated:
    """Create a link; the plaintext token is returned only here."""
    user, _ = auth
    share, token = share_service.create_share(
        db,
        owner=user,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        mode=body.mode,
        expires_in_hours=body.expires_in_hours,
        max_downloads=body.max_downloads,
        password=body.password,
    )
    db.commit()
    db.refresh(share)
    return ShareCreated(
        share=_share_info(db, user.id, share),
        token=token,
    )


@router.get("", response_model=ShareList)
def list_shares(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> ShareList:
    user, _ = auth
    return ShareList(items=share_service.list_shares(db, user_id=user.id))


@router.delete("/{share_id}")
def revoke_share(
    share_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, _ = auth
    share_service.revoke_share(db, user_id=user.id, share_id=share_id)
    db.commit()
    return {"revoked": share_id}


def _share_info(db: SAMSession, user_id: str, share) -> ShareInfo:
    rows = share_service.list_shares(db, user_id=user_id)
    for item in rows:
        if item["id"] == share.id:
            return ShareInfo(**item)
    raise RuntimeError("share vanished after commit")
