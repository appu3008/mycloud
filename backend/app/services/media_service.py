"""Photo/video library: media classification, metadata and albums.

Nothing about a file is guessed from its name: MIME type comes from the
server-side magic-byte sniff stored at upload time. EXIF is never parsed or
retained, so GPS metadata is always stripped. Image thumbnails are generated
locally with Pillow when it is installed; otherwise the original bytes are
served inline and the browser scales them. No external image service is used.
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import Settings
from ..models import Album, AlbumFile, File, MediaMetadata, new_id, utcnow
from ..storage import blob_store

PHOTO_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
VIDEO_MIMES = {"video/mp4", "video/webm", "video/quicktime", "video/x-msvideo"}
THUMB_WIDTH = 320


def kind_of(mime_type: str) -> str | None:
    if mime_type in PHOTO_MIMES:
        return "photo"
    if mime_type in VIDEO_MIMES:
        return "video"
    return None


def _dimensions(head: bytes) -> tuple[int | None, int | None]:
    """Read PNG/JPEG pixel size from the leading bytes (no full-file load)."""
    if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
        width, height = struct.unpack(">II", head[16:24])
        return int(width), int(height)
    if head.startswith(b"\xff\xd8\xff"):
        index = 2
        while index + 9 < len(head):
            if head[index] != 0xFF:
                index += 1
                continue
            marker = head[index + 1]
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            length = struct.unpack(">H", head[index + 2:index + 4])[0]
            if marker in range(0xC0, 0xC4):
                height, width = struct.unpack(">HH", head[index + 5:index + 9])
                return int(width), int(height)
            index += 2 + length
    return None, None


def ensure_metadata(db: SAMSession, settings: Settings, file_row: File) -> MediaMetadata | None:
    """Create a media row for a newly uploaded photo/video (idempotent)."""
    kind = kind_of(file_row.mime_type)
    if kind is None:
        return None
    existing = db.get(MediaMetadata, file_row.id)
    if existing is not None:
        return existing
    head = b"".join(blob_store.open_blob_stream(settings, file_row.blob_sha256, 0, 64 * 1024))
    width, height = _dimensions(head)
    metadata = MediaMetadata(
        file_id=file_row.id,
        kind=kind,
        width=width,
        height=height,
        duration_seconds=None,  # never guessed: video duration needs a demuxer
        captured_at=None,
        exif_json="{}",
        gps_stripped=True,
        thumbnail_path=None,
        created_at=utcnow(),
    )
    db.add(metadata)
    return metadata


def _metadata_of(db: SAMSession, file_row: File) -> dict:
    row = db.get(MediaMetadata, file_row.id)
    return {
        "width": row.width if row else None,
        "height": row.height if row else None,
        "duration_seconds": row.duration_seconds if row else None,
        "gps_stripped": row.gps_stripped if row else True,
        "has_thumbnail": bool(
            row and (row.thumbnail_path or file_row.mime_type in PHOTO_MIMES)
        ),
        "kind": row.kind if row else kind_of(file_row.mime_type),
    }


def list_media(
    db: SAMSession,
    *,
    user_id: str,
    kind: str,
    album_id: str | None = None,
) -> list[dict]:
    stmt = (
        select(File)
        .where(File.owner_id == user_id, File.deleted_at.is_(None))
        .order_by(File.mtime.desc())
    )
    if album_id:
        album = owned_album(db, user_id=user_id, album_id=album_id)
        stmt = stmt.join(
            AlbumFile,
            (AlbumFile.file_id == File.id) & (AlbumFile.album_id == album.id),
        )
    rows = db.execute(stmt).scalars().all()
    result = []
    for row in rows:
        info = _metadata_of(db, row)
        if info["kind"] != kind:
            continue
        result.append(
            {
                "id": row.id,
                "name": row.name,
                "mime_type": row.mime_type,
                "size_bytes": row.size_bytes,
                "mtime": row.mtime,
                **info,
            }
        )
    return result


# --- albums ---------------------------------------------------------------------

def create_album(db: SAMSession, *, user_id: str, name: str, description: str = "") -> Album:
    clean = name.strip()[:128]
    if not clean:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_name"})
    duplicate = db.execute(
        select(Album).where(Album.owner_id == user_id, Album.name == clean)
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "album_exists"})
    album = Album(
        id=new_id(), owner_id=user_id, name=clean, description=description[:1024],
        cover_file_id=None, created_at=utcnow(), updated_at=utcnow(),
    )
    db.add(album)
    return album


def owned_album(db: SAMSession, *, user_id: str, album_id: str) -> Album:
    album = db.get(Album, album_id)
    if album is None or album.owner_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "album_not_found"})
    return album


def album_dict(db: SAMSession, album: Album) -> dict:
    count = db.execute(
        select(AlbumFile).where(AlbumFile.album_id == album.id)
    ).scalars().all()
    files = db.execute(
        select(File).where(File.id.in_([row.file_id for row in count]))
    ).scalars().all()
    total = sum(row.size_bytes for row in files)
    return {
        "id": album.id,
        "name": album.name,
        "description": album.description,
        "cover_file_id": album.cover_file_id,
        "file_count": len(count),
        "total_bytes": total,
        "created_at": album.created_at,
    }


def list_albums(db: SAMSession, *, user_id: str) -> list[dict]:
    rows = db.execute(
        select(Album).where(Album.owner_id == user_id).order_by(Album.name.asc())
    ).scalars().all()
    return [album_dict(db, row) for row in rows]


def add_files(db: SAMSession, *, user_id: str, album_id: str, file_ids: list[str]) -> dict:
    album = owned_album(db, user_id=user_id, album_id=album_id)
    added = 0
    for file_id in dict.fromkeys(file_ids):
        file_row = db.get(File, file_id)
        if file_row is None or file_row.owner_id != user_id or file_row.deleted_at is not None:
            continue
        exists = db.get(AlbumFile, {"album_id": album.id, "file_id": file_id})
        if exists:
            continue
        db.add(AlbumFile(album_id=album.id, file_id=file_id, added_at=utcnow()))
        if album.cover_file_id is None:
            album.cover_file_id = file_id
        added += 1
    return {"added": added}


def remove_file(db: SAMSession, *, user_id: str, album_id: str, file_id: str) -> dict:
    album = owned_album(db, user_id=user_id, album_id=album_id)
    row = db.get(AlbumFile, {"album_id": album.id, "file_id": file_id})
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "file_not_in_album"})
    db.delete(row)
    if album.cover_file_id == file_id:
        album.cover_file_id = None
    return {"removed": file_id}


def delete_album(db: SAMSession, *, user_id: str, album_id: str) -> dict:
    album = owned_album(db, user_id=user_id, album_id=album_id)
    db.delete(album)
    return {"deleted": album_id}


# --- thumbnails --------------------------------------------------------------------

def thumbnail_abs_path(settings: Settings, file_row: File) -> Path | None:
    """Generate a cached Pillow thumbnail when available; else None."""
    try:
        from PIL import Image
    except ImportError:
        return None
    if file_row.mime_type not in PHOTO_MIMES:
        return None
    target_dir = settings.data_dir / "thumbs"
    target = target_dir / f"{file_row.blob_sha256}-{THUMB_WIDTH}.jpg"
    if target.is_file():
        return target
    target_dir.mkdir(parents=True, exist_ok=True)
    data = b"".join(blob_store.open_blob_stream(settings, file_row.blob_sha256, 0, None))
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.thumbnail((THUMB_WIDTH, THUMB_WIDTH))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(target, format="JPEG", quality=78)
    except Exception:
        return None
    return target
