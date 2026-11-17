"""Pydantic schemas for share links (creation, listing, public metadata)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .uploads import FileInfo


class ShareCreate(BaseModel):
    """Create a share link for a file or folder."""

    model_config = ConfigDict(extra="forbid")

    resource_type: Literal["file", "folder"]
    resource_id: str = Field(min_length=1, max_length=64)
    mode: Literal["download", "readonly"] = "download"
    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 90)
    max_downloads: int | None = Field(default=None, ge=1, le=10_000)
    password: str | None = Field(default=None, min_length=4, max_length=128)


class ShareInfo(BaseModel):
    """A share link as its owner sees it (token never included)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    resource_type: str
    file_id: str | None
    folder_id: str | None
    resource_name: str
    mode: str
    password_protected: bool
    max_downloads: int | None
    download_count: int
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ShareCreated(BaseModel):
    """Creation result: the plaintext token is returned exactly once."""

    share: ShareInfo
    token: str


class ShareList(BaseModel):
    items: list[ShareInfo] = []


class PublicShareMeta(BaseModel):
    """What a link recipient sees (no owner internals)."""

    kind: Literal["file", "folder"]
    name: str
    owner_name: str
    size_bytes: int = 0
    has_password: bool
    expires_at: datetime | None
    downloads_remaining: int | None = None


class PublicShareItem(BaseModel):
    """One file inside a publicly shared folder."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    size_bytes: int
    mtime: datetime


class PublicShareItems(BaseModel):
    folder: PublicShareMeta
    items: list[PublicShareItem] = []
