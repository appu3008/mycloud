"""Pydantic schemas for media listings and albums."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MediaItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mime_type: str
    size_bytes: int
    mtime: datetime
    kind: Literal["photo", "video"] | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    gps_stripped: bool
    has_thumbnail: bool


class MediaList(BaseModel):
    items: list[MediaItem] = []
    total: int = 0


class AlbumCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)


class AlbumFiles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_ids: list[str] = Field(default_factory=list, max_length=500)


class AlbumInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    cover_file_id: str | None
    file_count: int
    total_bytes: int
    created_at: datetime


class AlbumList(BaseModel):
    items: list[AlbumInfo] = []
