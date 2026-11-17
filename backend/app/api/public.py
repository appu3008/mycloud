"""Public share endpoints (v1, unauthenticated): metadata + downloads.

Recipients get the token from its owner; everything here resolves by the
token's hash, counts downloads, and 410s on revoked/expired/exhausted
links. Password-protected links require the password on every download.
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as SAMSession
from starlette.responses import StreamingResponse

from ..core.config import get_settings
from ..core.database import get_db
from ..schemas.shares import (
    PublicShareItems,
    PublicShareMeta,
    PublicShareItem,
)
from ..services import share_service
from ..storage import blob_store
from .files import _content_disposition, _etag_of

router = APIRouter(prefix="/public", tags=["public"])


def _password_of(request: Request) -> str | None:
    raw = request.query_params.get("password")
    return urllib.parse.unquote(raw) if raw else None


def _meta(db, share) -> PublicShareMeta:
    resource = share_service.ensure_resource_available(db, share)
    from ..models import User

    owner_name = (
        db.get(User, share.owner_id).display_name if share.owner_id else "unknown"
    )
    remaining = (
        max(0, share.max_downloads - share.download_count)
        if share.max_downloads is not None
        else None
    )
    if share.resource_type == "file":
        return PublicShareMeta(
            kind="file",
            name=resource.name,
            owner_name=owner_name,
            size_bytes=resource.size_bytes,
            has_password=share.password_hash is not None,
            expires_at=share.expires_at,
            downloads_remaining=remaining,
        )
    items = share_service.folder_items(db, share)
    return PublicShareMeta(
        kind="folder",
        name=resource.name,
        owner_name=owner_name,
        size_bytes=sum(item.size_bytes for item in items),
        has_password=share.password_hash is not None,
        expires_at=share.expires_at,
        downloads_remaining=remaining,
    )


@router.get("/shares/{token}", response_model=PublicShareMeta)
def share_meta(token: str, db: SAMSession = Depends(get_db)) -> PublicShareMeta:
    share = share_service.resolve_public(db, token)
    return _meta(db, share)


@router.get("/shares/{token}/items", response_model=PublicShareItems)
def share_items(token: str, request: Request, db: SAMSession = Depends(get_db)) -> PublicShareItems:
    share = share_service.resolve_public(db, token)
    share_service.ensure_password_ok(share, _password_of(request))
    meta = _meta(db, share)
    items = [
        PublicShareItem.model_validate(row)
        for row in share_service.folder_items(db, share)
    ]
    return PublicShareItems(folder=meta, items=items)


def _stream_file(file_row, request: Request) -> Response:
    blob = file_row.blob
    headers = {
        "ETag": _etag_of(blob.sha256),
        "Content-Disposition": _content_disposition(file_row.name),
        "Cache-Control": "private, no-store",
    }
    stream = blob_store.open_blob_stream(get_settings(), blob.sha256, 0, None)
    return StreamingResponse(
        stream,
        media_type=file_row.mime_type,
        headers=headers,
    )


@router.get("/shares/{token}/download")
def share_download(
    token: str, request: Request, db: SAMSession = Depends(get_db)
) -> Response:
    """Download the shared file (folder shares are not a single file)."""
    share = share_service.resolve_public(db, token)
    share_service.ensure_password_ok(share, _password_of(request))
    resource = share_service.ensure_resource_available(db, share)

    if share.resource_type != "file":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"error": "not_a_file_share"}
        )
    share_service.register_download(db, share, f"Share of \u201c{resource.name}\u201d downloaded")
    db.commit()
    return _stream_file(resource, request)


@router.get("/shares/{token}/items/{file_id}/download")
def share_folder_item_download(
    token: str, file_id: str, request: Request, db: SAMSession = Depends(get_db)
) -> Response:
    share = share_service.resolve_public(db, token)
    share_service.ensure_password_ok(share, _password_of(request))
    if share.resource_type != "folder":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"error": "not_a_folder_share"}
        )
    items = share_service.folder_items(db, share)
    target = next((row for row in items if row.id == file_id), None)
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"error": "file_not_in_share"}
        )
    share_service.register_download(
        db, share, f"Shared file \u201c{target.name}\u201d downloaded"
    )
    db.commit()
    return _stream_file(target, request)
