"""Pydantic schemas for storage analytics + duplicate detection."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .uploads import FileInfo


class StorageUsage(BaseModel):
    """Live per-user storage picture (real numbers only)."""

    used_bytes: int
    quota_bytes: int
    file_count: int
    folder_count: int
    trash_files: int
    trash_bytes: int


class DuplicateItem(BaseModel):
    """One file inside a duplicate group."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    folder_id: str | None
    size_bytes: int
    created_at: datetime
    mtime: datetime


class DuplicateGroup(BaseModel):
    """Files sharing identical content (same content-addressed blob)."""

    sha256: str
    size_bytes: int
    copies: int
    wasted_bytes: int
    items: list[DuplicateItem]


class DuplicatesReport(BaseModel):
    groups: list[DuplicateGroup] = []
    group_count: int = 0
    total_wasted_bytes: int = 0
