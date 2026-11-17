"""Pydantic schemas for the recycle bin (trash) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrashFile(BaseModel):
    """Deleted file as shown in the recycle bin (adds ``deleted_at``)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    extension: str
    mime_type: str
    size_bytes: int
    folder_id: str | None
    created_at: datetime
    updated_at: datetime
    mtime: datetime
    is_favorite: bool
    deleted_at: datetime


class TrashFolder(BaseModel):
    """Deleted folder as shown in the recycle bin (adds ``deleted_at``)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    name: str
    path: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime


class TrashContents(BaseModel):
    """Top-level deleted items: every deleted folder, plus deleted files
    whose containing folder is NOT deleted (those restore via the folder)."""

    files: list[TrashFile] = Field(default_factory=list)
    folders: list[TrashFolder] = Field(default_factory=list)
    total_bytes: int = 0


class TrashRestore(BaseModel):
    """Batch restore from the recycle bin."""

    model_config = ConfigDict(extra="forbid")

    file_ids: list[str] = Field(default_factory=list, max_length=200)
    folder_ids: list[str] = Field(default_factory=list, max_length=200)


class TrashPurge(BaseModel):
    """Permanent deletion. ``all=True`` empties the whole bin (files and
    folders lists are then ignored)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["items", "all"] = "items"
    file_ids: list[str] = Field(default_factory=list, max_length=200)
    folder_ids: list[str] = Field(default_factory=list, max_length=200)


class TrashCounts(BaseModel):
    files: int = 0
    folders: int = 0
    bytes_freed: int = 0
