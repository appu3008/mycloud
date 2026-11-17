"""Share-link service: creation, listing, revocation, public resolution.

Tokens are random and only their SHA-256 is stored (same convention as
session cookies), so a database leak does not expose working links. The
plaintext token is returned to the caller exactly once, at creation.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..models import ActivityEvent, File, Folder, Share, User, new_id, utcnow
from ..security.password import hash_password, verify_password
from . import auth_service, file_service, folder_service

_TOKEN_BYTES = 24


class ShareUnavailable(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_410_GONE, detail={"error": detail})


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _activity(db: SAMSession, *, user_id: str, summary: str, file_id: str | None) -> None:
    db.add(
        ActivityEvent(
            user_id=user_id,
            kind="share",
            file_id=file_id,
            summary=summary,
            created_at=utcnow(),
        )
    )


def create_share(
    db: SAMSession,
    *,
    owner: User,
    resource_type: str,
    resource_id: str,
    mode: str = "download",
    expires_in_hours: int | None = None,
    max_downloads: int | None = None,
    password: str | None = None,
) -> tuple[Share, str]:
    """Create a share link; returns (row, plaintext token)."""
    if resource_type == "file":
        row = file_service.get_file_owned(db, user_id=owner.id, file_id=resource_id)
        file_id, folder_id, name = row.id, None, row.name
    else:
        row = folder_service.get_folder_owned(
            db, user_id=owner.id, folder_id=resource_id
        )
        file_id, folder_id, name = None, row.id, row.name

    token = _new_token()
    share = Share(
        id=new_id(),
        owner_id=owner.id,
        resource_type=resource_type,
        file_id=file_id,
        folder_id=folder_id,
        token_hash=auth_service.hash_cookie_token(token),
        mode=mode,
        password_hash=hash_password(password) if password else None,
        max_downloads=max_downloads,
        expires_at=utcnow() + timedelta(hours=expires_in_hours) if expires_in_hours else None,
        download_count=0,
        created_at=utcnow(),
    )
    db.add(share)
    _activity(
        db,
        user_id=owner.id,
        file_id=share.file_id,
        summary=f"Shared {resource_type} \u201c{name}\u201d",
    )
    return share, token


def owned_share(db: SAMSession, *, user_id: str, share_id: str) -> Share:
    share = db.get(Share, share_id)
    if share is None or share.owner_id != user_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"error": "share_not_found"}
        )
    return share


def list_shares(db: SAMSession, *, user_id: str) -> list[dict]:
    rows = db.execute(
        select(Share)
        .where(Share.owner_id == user_id)
        .order_by(Share.created_at.desc())
    ).scalars().all()

    file_names = {
        row.id: row.name
        for row in db.execute(select(File).where(File.owner_id == user_id)).scalars().all()
    }
    folder_names = {
        row.id: row.name
        for row in db.execute(select(Folder).where(Folder.owner_id == user_id)).scalars().all()
    }

    items = []
    for share in rows:
        name = (
            file_names.get(share.file_id)
            if share.file_id
            else folder_names.get(share.folder_id)
        )
        items.append(
            {
                "id": share.id,
                "resource_type": share.resource_type,
                "file_id": share.file_id,
                "folder_id": share.folder_id,
                "resource_name": name or "(deleted)",
                "mode": share.mode,
                "password_protected": share.password_hash is not None,
                "max_downloads": share.max_downloads,
                "download_count": share.download_count,
                "expires_at": share.expires_at,
                "revoked_at": share.revoked_at,
                "created_at": share.created_at,
            }
        )
    return items


def revoke_share(db: SAMSession, *, user_id: str, share_id: str) -> Share:
    share = owned_share(db, user_id=user_id, share_id=share_id)
    if share.revoked_at is None:
        share.revoked_at = utcnow()
    return share


# --- public resolution ---------------------------------------------------------


def resolve_public(db: SAMSession, token: str) -> Share:
    """Look a token up and enforce revocation/expiry (410s)."""
    share = db.execute(
        select(Share).where(Share.token_hash == auth_service.hash_cookie_token(token))
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "share_not_found"})
    if share.revoked_at is not None:
        raise ShareUnavailable("share_revoked")
    if share.expires_at is not None and share.expires_at < utcnow():
        raise ShareUnavailable("share_expired")
    if share.max_downloads is not None and share.download_count >= share.max_downloads:
        raise ShareUnavailable("share_exhausted")
    return share


def ensure_password_ok(share: Share, password: str | None) -> None:
    if share.password_hash is None:
        return
    if not password or not verify_password(password, share.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail={"error": "share_password_required"}
        )


def ensure_resource_available(db: SAMSession, share: Share) -> File | Folder:
    """The shared file (or folder) must still exist and be live."""
    if share.file_id is not None:
        file_row = db.get(File, share.file_id)
        if file_row is None or file_row.deleted_at is not None:
            raise ShareUnavailable("resource_unavailable")
        return file_row
    folder = db.get(Folder, share.folder_id)  # type: ignore[arg-type]
    if folder is None or folder.deleted_at is not None:
        raise ShareUnavailable("resource_unavailable")
    return folder


def register_download(db: SAMSession, share: Share, summary: str) -> None:
    share.download_count += 1
    _activity(db, user_id=share.owner_id, file_id=share.file_id, summary=summary)


def folder_items(db: SAMSession, share: Share) -> list[File]:
    """Live files directly inside the shared folder (stable name order)."""
    folder = ensure_resource_available(db, share)
    assert isinstance(folder, Folder)
    return list(
        db.execute(
            select(File)
            .where(
                File.owner_id == share.owner_id,
                File.folder_id == folder.id,
                File.deleted_at.is_(None),
            )
            .order_by(File.name.asc())
        ).scalars()
    )
