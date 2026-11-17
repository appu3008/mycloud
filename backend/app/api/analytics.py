"""Storage analytics API (v1): usage vs quota and exact-duplicate report."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SAMSession

from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas.analytics import DuplicatesReport, StorageUsage
from ..services import analytics_service
from .dependencies import get_current_auth

router = APIRouter(tags=["analytics"])


@router.get("/storage/usage", response_model=StorageUsage)
def storage_usage(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> StorageUsage:
    """The signed-in user's live storage picture."""
    user, _ = auth
    return StorageUsage(**analytics_service.storage_usage(db, user_id=user.id))


@router.get("/duplicates", response_model=DuplicatesReport)
def duplicates_report(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> DuplicatesReport:
    """Files sharing identical content, biggest waste first."""
    user, _ = auth
    return DuplicatesReport(**analytics_service.duplicate_groups(db, user_id=user.id))
