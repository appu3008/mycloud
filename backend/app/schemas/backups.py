"""Pydantic schemas for backup jobs and runs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BackupJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    target_path: str | None = Field(default=None, max_length=512)
    include_content_blobs: bool = True
    retention_count: int = Field(default=3, ge=1, le=50)
    schedule_cron: str | None = Field(default=None, max_length=64)


class BackupJobInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    target_path: str
    include_content_blobs: bool
    retention_count: int
    schedule_cron: str | None
    enabled: bool
    backup_count: int
    created_at: datetime


class BackupJobList(BaseModel):
    items: list[BackupJobInfo] = []


class BackupRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    size_bytes: int
    state: Literal["running", "verified", "failed"]
    destination: str
    started_at: datetime
    finished_at: datetime | None


class BackupRunList(BaseModel):
    items: list[BackupRun] = []
