"""Files API (v1): ownership-scoped listing, metadata, range download.

Downloads stream from the content-addressed blob store (never whole-file
buffered). Range support follows RFC 9110 single-range semantics; content is
immutable, so ETag is derived from the blob's SHA-256.
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as SAMSession

from ..core.config import get_settings
from ..core.database import get_db
from ..models import ContentBlob, User
from ..models import Session as SessionRow
from ..schemas.uploads import FileInfo
from ..services import file_service
from ..storage import blob_store
from .dependencies import get_current_auth

router = APIRouter(prefix="/files", tags=["files"])


def _etag_of(blob_sha256: str) -> str:
    """Strong validator: content-addressed blobs are immutable."""
    return f'"{blob_sha256[:32]}"'


def _content_disposition(name: str) -> str:
    ascii_name = name.encode("ascii", "ignore").decode() or "file"
    quoted = urllib.parse.quote(name)
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'


def _load_owned_file(db: SAMSession, user_id: str, file_id: str):
    file_row = file_service.get_file_owned(db, user_id=user_id, file_id=file_id)
    blob = db.get(ContentBlob, file_row.blob_sha256)
    if blob is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"error": "content_missing"}
        )
    return file_row, blob


def _parse_range_or_none(request: Request, size: int) -> tuple[int, int | None] | None:
    """Wrapper so Range parse errors surface as 416 with proper headers."""
    header = request.headers.get("range")
    try:
        parsed = file_service.parse_range_header(header, size)
    except HTTPException as exc:
        if size > 0:
            raise HTTPException(
                status.HTTP_416_RANGE_NOT_SATISFIABLE,
                detail=exc.detail,
                headers={"Content-Range": f"bytes */{size}"},
            ) from exc
        raise
    return parsed


@router.get("/{file_id}/content")
def download_content(
    file_id: str,
    request: Request,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> Response:
    user, _ = auth
    file_row, blob = _load_owned_file(db, user.id, file_id)

    etag = _etag_of(blob.sha256)
    if request.headers.get("if-none-match", "").strip() == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag, "Accept-Ranges": "bytes"},
        )

    total = blob.size_bytes
    parsed_range = _parse_range_or_none(request, total)
    settings = get_settings()
    headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Content-Disposition": _content_disposition(file_row.name),
        "Cache-Control": "private, max-age=31536000, immutable",
    }

    if parsed_range is None:
        stream = blob_store.open_blob_stream(settings, blob.sha256, 0, None)
        length = total
    else:
        start, end_inclusive = parsed_range
        end = end_inclusive if end_inclusive is not None else total - 1
        stream = blob_store.open_blob_stream(settings, blob.sha256, start, end + 1)
        length = end - start + 1
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"

    headers["Content-Length"] = str(length)

    # Activity emission lands with the timeline phase; downloads counted then.
    return StreamingResponse(
        stream,
        media_type=file_row.mime_type,
        headers=headers,
        status_code=200 if parsed_range is None else 206,
    )


@router.get("/{file_id}", response_model=FileInfo)
def file_metadata(
    file_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> FileInfo:
    user, _ = auth
    file_row, _blob = _load_owned_file(db, user.id, file_id)
    return FileInfo.model_validate(file_row)
