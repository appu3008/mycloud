"""Pydantic schemas for devices and sync jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    platform: str = Field(default="generic", max_length=32)
    public_key: str | None = Field(default=None, max_length=512)


class DeviceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_level: Literal["trusted", "untrusted"] | None = None
    can_sync: bool | None = None
    can_backup: bool | None = None
    revoke: bool = False


class DeviceInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    platform: str
    has_public_key: bool
    trust_level: str
    can_sync: bool
    can_backup: bool
    last_seen_at: datetime | None
    revoked_at: datetime | None
    job_count: int
    conflict_count: int


class DeviceList(BaseModel):
    items: list[DeviceInfo] = []


class BackupConfig(BaseModel):
    device_id: str
    device_name: str
    upload_endpoint: str
    chunk_endpoint: str
    complete_endpoint: str
    auth: str
    chunk_checksum_header: str
    max_chunk_mb: int
    trust_level: str


class SyncJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=64)
    file_id: str = Field(min_length=1, max_length=64)
    direction: Literal["up", "down"]
    local_checksum: str | None = Field(default=None, max_length=64)
    conflict_strategy: Literal[
        "accept_local", "accept_server", "newer_wins", "conflict_copy"
    ] | None = None


class SyncJobComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checksum: str | None = Field(default=None, max_length=64)


class SyncJobResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["accept_local", "accept_server", "newer_wins", "conflict_copy"]


class SyncJobInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    file_id: str
    direction: str
    state: str
    local_checksum: str | None
    server_checksum: str | None
    conflict_strategy: str | None
    attempts: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class SyncJobList(BaseModel):
    items: list[SyncJobInfo] = []
