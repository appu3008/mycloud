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
from ..models import ContentBlob, File, User, new_id, utcnow
from ..models import Session as SessionRow
from ..schemas.folders import FileBatch, FileRename
from ..schemas.uploads import FileInfo
from ..services import activity_service, file_service, folder_service
from ..services.upload_service import UploadRejected
from ..storage import blob_store
from ..storage.mime import extension_of
from .dependencies import csrf_protected_auth, get_current_auth

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


@router.get("")
def list_files(
    folder_id: str | None = None,
    search: str | None = None,
    sort: str = "name",
    order: str = "asc",
    page: int = 0,
    page_size: int = 50,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    """Folder listing (root when folder_id omitted), ownership-scoped."""
    user, _ = auth
    # Ownership check happens inside folder_owned for non-root folders.
    file_service.folder_owned(db, user_id=user.id, folder_id=folder_id)
    page_size = max(1, min(page_size, 200))
    rows, total = file_service.list_folder_files(
        db,
        user_id=user.id,
        folder_id=folder_id,
        limit=page_size,
        offset=page * page_size,
        sort=sort,
        order=order,
    )
    return {
        "items": [FileInfo.model_validate(row).model_dump() for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/{file_id}", response_model=FileInfo)
def rename_file(
    file_id: str,
    body: FileRename,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> FileInfo:
    user, _ = auth
    file_row, _blob = _load_owned_file(db, user.id, file_id)
    if body.name != file_row.name:
        file_row.name = body.name
        file_row.extension = extension_of(body.name)
        file_row.updated_at = utcnow()
    db.commit()
    return FileInfo.model_validate(file_row)


@router.post("/batch")
def batch_files(
    body: FileBatch,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    """Multi-select operations: move / copy / delete / restore / favorite.

    Copy re-points a new row at the same immutable blob (ref_count++), so it
    costs only quota, never bytes. Quota and target-folder ownership are
    enforced exactly like uploads.
    """
    user, _ = auth
    unique_ids = list(dict.fromkeys(body.file_ids))
    owned = folder_service.owned_files_by_id(db, user.id, unique_ids)
    missing = [fid for fid in unique_ids if fid not in owned]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "file_not_found", "missing": missing[:10]},
        )

    target_needed = body.action in ("move", "copy")
    if target_needed:
        file_service.folder_owned(db, user_id=user.id, folder_id=body.target_folder_id)

    updated = 0
    if body.action == "copy":
        settings = get_settings()
        total_incoming = sum(owned[fid].size_bytes for fid in unique_ids)
        try:
            folder_service.assert_within_quota(db, settings, user.id, total_incoming)
        except UploadRejected as exc:
            raise _failure_from_rejection(exc) from exc

    for fid in unique_ids:
        row = owned[fid]
        if body.action == "move":
            if row.deleted_at is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, detail={"error": "file_in_recycle_bin"}
                )
            row.folder_id = body.target_folder_id
        elif body.action == "copy":
            if row.deleted_at is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, detail={"error": "file_in_recycle_bin"}
                )
            blob = db.get(ContentBlob, row.blob_sha256)
            if blob is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail={"error": "content_missing"}
                )
            new_row = File(
                id=new_id(),
                owner_id=user.id,
                folder_id=body.target_folder_id,
                name=folder_service.unique_copy_name(
                    db, user_id=user.id, folder_id=body.target_folder_id, name=row.name
                ),
                extension=row.extension,
                mime_type=row.mime_type,
                size_bytes=row.size_bytes,
                blob_sha256=row.blob_sha256,
                mtime=utcnow(),
            )
            db.add(new_row)
            blob.ref_count += 1
        elif body.action == "delete":
            if row.deleted_at is None:
                file_service.soft_delete_file(db, row)
                activity_service.log_event(
                    db, user_id=user.id, kind="delete",
                    summary=f"Moved \u201c{row.name}\u201d to the recycle bin",
                    file_id=row.id,
                )
        elif body.action == "restore":
            file_service.restore_file(db, row)
            activity_service.log_event(
                db, user_id=user.id, kind="restore",
                summary=f"Restored \u201c{row.name}\u201d",
                file_id=row.id,
            )
        elif body.action == "favorite":
            row.is_favorite = True
        elif body.action == "unfavorite":
            row.is_favorite = False
        row.updated_at = utcnow()
        updated += 1
    db.commit()
    return {"updated": updated}


def _failure_from_rejection(exc: UploadRejected) -> HTTPException:
    """Map upload-style rejections onto the same status codes uploads use."""
    mapping = {
        "quota_exceeded": status.HTTP_413_CONTENT_TOO_LARGE,
        "file_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
        "disk_protected": status.HTTP_507_INSUFFICIENT_STORAGE,
    }
    return HTTPException(
        mapping.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"error": exc.code, "message": exc.detail},
    )
