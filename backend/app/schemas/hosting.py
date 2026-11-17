"""Pydantic schemas for the hosting app manager."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HostedAppCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="static", pattern="^(static|proxy)$")
    domain: str = Field(default="localhost", max_length=255)
    path_prefix: str = Field(default="/", max_length=255)
    upstream_port: int | None = Field(default=None, ge=1, le=65535)
    description: str = Field(default="", max_length=512)


class HostedAppUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    description: str | None = Field(default=None, max_length=512)


class HostedAppInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    domain: str
    path_prefix: str
    upstream_port: int | None
    root_path: str | None
    enabled: bool
    description: str
    created_at: datetime


class HostedAppList(BaseModel):
    items: list[HostedAppInfo] = []


class StaticFileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=1_048_576)
