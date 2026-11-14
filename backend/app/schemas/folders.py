"""Pydantic schemas for folders and batch file operations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_FOLDER_NAME = 255


def _clean_folder_name(value: str) -> str:
    """Folder names are single path segments: no separators, no traversal."""
    if value != value.strip() or not value.strip():
        raise ValueError("folder name must not be empty or start/end with spaces")
    if "/" in value or "\\" in value or ".." in value or "\x00" in value:
        raise ValueError("folder name must not contain path separators")
    return value


class FolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_FOLDER_NAME)
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _clean_folder_name(value)


class FolderRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_FOLDER_NAME)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _clean_folder_name(value)


class FolderMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: str | None = None


class FolderInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    name: str
    path: str
    created_at: datetime
    updated_at: datetime


class FolderDetail(FolderInfo):
    breadcrumb: list[FolderInfo] = Field(default_factory=list)


class FolderBatch(BaseModel):
    """Multi-select operations on folders (delete/restore/move)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["delete", "restore", "move"]
    folder_ids: list[str] = Field(min_length=1, max_length=200)
    parent_id: str | None = None  # target for move


class FileRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=512)

    @field_validator("name")
    @classmethod
    def _no_path_parts(cls, value: str) -> str:
        if "/" in value or "\\" in value or ".." in value or "\x00" in value:
            raise ValueError("name must not contain path separators")
        return value


class FileBatch(BaseModel):
    """Multi-select operations on files."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["delete", "restore", "move", "copy", "favorite", "unfavorite"]
    file_ids: list[str] = Field(min_length=1, max_length=200)
    target_folder_id: str | None = None  # destination for move/copy
