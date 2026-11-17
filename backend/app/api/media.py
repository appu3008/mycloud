"""Media API (v1): photo/video listings, inline thumbnails, albums."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as SessionSAM

from ..core.config import get_settings
from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import File, User
from ..schemas.media import (
    AlbumCreate,
    AlbumFiles,
    AlbumInfo,
    AlbumList,
    MediaItem,
    MediaList,
)
from ..services import activity_service, media_service
from ..storage import blob_store
from .dependencies import csrf_protected_auth, get_current_auth

media_router = APIRouter(prefix="/media", tags=["media"])
albums_router = APIRouter(prefix="/albums", tags=["albums"])


@media_router.get("/photos", response_model=MediaList)
def photos(
    album_id: str | None = None,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> MediaList:
    user, _ = auth
    items = media_service.list_media(db, user_id=user.id, kind="photo", album_id=album_id)
    return MediaList(items=[MediaItem(**row) for row in items], total=len(items))


@media_router.get("/videos", response_model=MediaList)
def videos(
    album_id: str | None = None,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> MediaList:
    user, _ = auth
    items = media_service.list_media(db, user_id=user.id, kind="video", album_id=album_id)
    return MediaList(items=[MediaItem(**row) for row in items], total=len(items))


@media_router.get("/{file_id}/thumbnail", response_model=None)
def thumbnail(
    file_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> FileResponse | StreamingResponse:
    """Pillow thumbnail when available; original bytes inlined otherwise."""
    user, _ = auth
    file_row = db.execute(
        select(File).where(
            File.id == file_id, File.owner_id == user.id, File.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if file_row is None:
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "file_not_found"})
    generated = media_service.thumbnail_abs_path(get_settings(), file_row)
    if generated and Path(generated).is_file():
        return FileResponse(generated, media_type="image/jpeg")
    stream = blob_store.open_blob_stream(get_settings(), file_row.blob_sha256, 0, None)
    return StreamingResponse(stream, media_type=file_row.mime_type)


@albums_router.post("", response_model=AlbumInfo, status_code=201)
def create_album(
    body: AlbumCreate,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> AlbumInfo:
    user, _ = auth
    album = media_service.create_album(
        db, user_id=user.id, name=body.name, description=body.description
    )
    db.commit()
    return AlbumInfo(**media_service.album_dict(db, album))


@albums_router.get("", response_model=AlbumList)
def list_albums(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> AlbumList:
    user, _ = auth
    return AlbumList(items=[AlbumInfo(**row) for row in media_service.list_albums(db, user_id=user.id)])


@albums_router.post("/{album_id}/files", response_model=dict)
def add_to_album(
    album_id: str,
    body: AlbumFiles,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> dict:
    user, _ = auth
    result = media_service.add_files(
        db, user_id=user.id, album_id=album_id, file_ids=body.file_ids
    )
    activity_service.log_event(
        db, user_id=user.id, kind="folder",
        summary=f"Added {result['added']} file(s) to an album",
    )
    db.commit()
    return result


@albums_router.delete("/{album_id}/files/{file_id}", response_model=dict)
def remove_from_album(
    album_id: str,
    file_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> dict:
    user, _ = auth
    result = media_service.remove_file(
        db, user_id=user.id, album_id=album_id, file_id=file_id
    )
    db.commit()
    return result


@albums_router.delete("/{album_id}", response_model=dict)
def delete_album(
    album_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> dict:
    user, _ = auth
    result = media_service.delete_album(db, user_id=user.id, album_id=album_id)
    db.commit()
    return result
