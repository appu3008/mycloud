"""Activity timeline API (v1): the signed-in user's recent events."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as SAMSession

from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..services import activity_service
from .dependencies import get_current_auth

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    file_id: str | None
    summary: str
    created_at: datetime


class ActivityList(BaseModel):
    items: list[ActivityItem] = []
    total: int = 0


@router.get("", response_model=ActivityList)
def activity_timeline(
    limit: int = 50,
    page: int = 0,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> ActivityList:
    user, _ = auth
    events = activity_service.list_events(
        db, user_id=user.id, limit=limit, offset=max(0, page) * max(1, min(limit, 200))
    )
    return ActivityList(items=events["items"], total=events["total"])
