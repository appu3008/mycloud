"""Upload API (v1): resumable chunked uploads with server-verified integrity.

Body streaming: chunk PUTs are staged to temp files with a strict size cap
(RAM bounded regardless of client behavior), then validated by the service.
Mutating routes require the CSRF header (X-CSRF-Token).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import get_settings
from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import Upload, User
from ..schemas.uploads import (
    ChunkSaved,
    CompleteRequest,
    FileInfo,
    UploadInitRequest,
    UploadReserved,
    UploadState,
)
from ..services import activity_service, upload_service
from ..services.upload_service import UploadRejected
from .dependencies import (
    csrf_protected_auth,  # for mutating endpoints
    get_current_auth,  # for GET endpoints
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

_REJECTION_STATUS = {
    "quota_exceeded": status.HTTP_413_CONTENT_TOO_LARGE,
    "file_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
    "disk_protected": status.HTTP_507_INSUFFICIENT_STORAGE,
    "invalid_state": status.HTTP_409_CONFLICT,
    "missing_chunks": status.HTTP_409_CONFLICT,
    "folder_not_found": status.HTTP_404_NOT_FOUND,
    "chunk_out_of_range": status.HTTP_400_BAD_REQUEST,
    "invalid_chunk_hash": status.HTTP_400_BAD_REQUEST,
    "chunk_hash_mismatch": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "chunk_size_mismatch": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "chunk_conflict": status.HTTP_409_CONFLICT,
    "invalid_size": status.HTTP_400_BAD_REQUEST,
    "assembly_size_mismatch": status.HTTP_409_CONFLICT,
    "integrity_error": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _failure(code: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=_REJECTION_STATUS.get(code, status.HTTP_400_BAD_REQUEST),
        detail={"error": code, "message": detail},
    )


def _get_owned_upload(db: SAMSession, user_id: str, public_id: str) -> Upload:
    row = db.execute(
        select(Upload).where(
            Upload.client_upload_id == public_id, Upload.user_id == user_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"error": "upload_not_found"}
        )
    return row


@router.post("", response_model=UploadReserved, status_code=status.HTTP_201_CREATED)
async def init_upload(
    body: UploadInitRequest,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> UploadReserved:
    user, _ = auth
    try:
        row, public_id = upload_service.reserve(
            db,
            get_settings(),
            user=user,
            filename=body.filename,
            size_bytes=body.size_bytes,
            target_folder_id=body.target_folder_id,
            chunk_size_mb=body.chunk_size_mb,
        )
        db.commit()
        db.refresh(row)
    except UploadRejected as exc:
        db.rollback()
        raise _failure(exc.code, exc.detail) from exc
    return UploadReserved(
        upload_id=public_id,
        chunk_size=row.chunk_size_bytes,
        total_chunks=row.total_chunks,
        state=row.state,
    )


@router.get("/{public_id}", response_model=UploadState)
def upload_state(
    public_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> UploadState:
    user, _ = auth
    row = _get_owned_upload(db, user.id, public_id)
    return UploadState.model_validate(row)


@router.put("/{public_id}/chunks/{chunk_number}", response_model=ChunkSaved)
async def put_chunk(
    public_id: str,
    chunk_number: int,
    request: Request,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> ChunkSaved:
    user, _ = auth
    upload_row = _get_owned_upload(db, user.id, public_id)
    if upload_row.state == "aborted":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "upload_aborted"}
        )

    chunk_hash = request.headers.get("X-Chunk-Sha256", "")
    staged_path: Path | None = None
    try:
        staged_path = await _stage_request_body(request, cap=upload_row.chunk_size_bytes)
        saved = upload_service.accept_chunk(
            db,
            get_settings(),
            upload=upload_row,
            chunk_number=chunk_number,
            body=staged_path,
            body_sha256=chunk_hash,
        )
        db.commit()
        return ChunkSaved(
            chunk_number=saved.chunk_number,
            saved_at=saved.saved_at,
            received_chunks=upload_row.received_chunks,
        )
    except UploadRejected as exc:
        db.rollback()
        raise _failure(exc.code, exc.detail) from exc
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)


@router.post("/{public_id}/complete", response_model=FileInfo)
def complete_upload(
    public_id: str,
    body: CompleteRequest | None = None,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> FileInfo:
    user, _ = auth
    upload_row = _get_owned_upload(db, user.id, public_id)
    try:
        file_row = upload_service.complete(
            db,
            get_settings(),
            upload=upload_row,
            filename_override=body.filename if body else None,
            replace_file_id=body.replace_file_id if body else None,
        )
        db.commit()
    except UploadRejected as exc:
        db.rollback()
        raise _failure(exc.code, exc.detail) from exc
    activity_service.log_event(
        db, user_id=user.id, kind="upload",
        summary=f"Uploaded \u201c{file_row.name}\u201d",
        file_id=file_row.id,
    )
    from ..services import alert_service

    alert_service.evaluate_quota(db, user_id=user.id)
    db.commit()
    return FileInfo.model_validate(file_row)


@router.delete("/{public_id}")
def abort_upload(
    public_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, _ = auth
    row = _get_owned_upload(db, user.id, public_id)
    if row.state in ("complete", "aborted"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "invalid_state", "state": row.state}
        )
    upload_service.abort(db, get_settings(), upload=row)
    db.commit()
    return {"ok": True, "state": row.state}


async def _stage_request_body(request: Request, cap: int) -> Path:
    """Stream the request body to a temp file, hard-capped at `cap` bytes.

    Oversized bodies raise 413 immediately; the staging file is removed on
    any failure so the temp dir never accumulates rejected data.
    """
    total = 0
    staged_name: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".incoming") as staged:
            staged_name = Path(staged.name)
            async for block in request.stream():
                total += len(block)
                if total > cap:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        detail={"error": "chunk_too_large"},
                    )
                staged.write(block)
    except Exception:
        if staged_name is not None:
            staged_name.unlink(missing_ok=True)
        raise
    assert staged_name is not None  # reached only on success path
    return staged_name
