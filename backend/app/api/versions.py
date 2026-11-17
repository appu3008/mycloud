"""File version history API (v1): list, download and restore old content."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as SAMSession
from starlette.responses import StreamingResponse

from ..core.config import get_settings
from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..services import activity_service, version_service
from ..storage import blob_store
from .dependencies import csrf_protected_auth, get_current_auth

router = APIRouter(prefix="/files", tags=["versions"])


class VersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_number: int
    blob_sha256: str
    size_bytes: int
    created_by: str
    created_at: datetime


class VersionList(BaseModel):
    items: list[VersionItem] = []


@router.get("/{file_id}/versions", response_model=VersionList)
def list_versions(
    file_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> VersionList:
    user, _ = auth
    return VersionList(
        items=version_service.list_versions(db, user_id=user.id, file_id=file_id)
    )


@router.get("/{file_id}/versions/{version_id}/content")
def download_version(
    file_id: str,
    version_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> StreamingResponse:
    user, _ = auth
    version = version_service.owned_version(
        db, user_id=user.id, file_id=file_id, version_id=version_id
    )
    stream = blob_store.open_blob_stream(get_settings(), version.blob_sha256, 0, None)
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="version-{version.version_number}.bin"'},
    )


@router.post("/{file_id}/versions/{version_id}/restore", response_model=dict)
def restore_version(
    file_id: str,
    version_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, _ = auth
    file_row = version_service.restore_version(
        db, user_id=user.id, file_id=file_id, version_id=version_id
    )
    activity_service.log_event(
        db,
        user_id=user.id,
        kind="restore",
        summary=f"Restored version {version_id} of \u201c{file_row.name}\u201d",
        file_id=file_row.id,
    )
    db.commit()
    return {"restored": version_id, "blob_sha256": file_row.blob_sha256}
