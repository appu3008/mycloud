"""Pydantic schemas for uploads and files."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UploadInitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(gt=0, le=2**63)
    target_folder_id: str | None = None
    chunk_size_mb: int | None = Field(default=None, ge=1, le=64)

    @field_validator("filename")
    @classmethod
    def _no_path_parts(cls, value: str) -> str:
        if "/" in value or "\\" in value or ".." in value or "\x00" in value:
            raise ValueError("filename must not contain path separators")
        return value


class UploadReserved(BaseModel):
    upload_id: str
    chunk_size: int
    total_chunks: int
    state: str


class ChunkSaved(BaseModel):
    chunk_number: int
    saved_at: datetime
    received_chunks: int


class UploadState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    upload_id: str = Field(validation_alias="client_upload_id")
    filename: str
    size_bytes: int
    chunk_size_bytes: int
    total_chunks: int
    received_chunks: int
    state: str


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str | None = Field(default=None, max_length=512)
    replace_file_id: str | None = Field(default=None, max_length=64)


class FileInfo(BaseModel):
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
