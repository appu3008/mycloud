"""Pydantic schemas for authorized network auditing."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScopeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    cidr: str = Field(min_length=3, max_length=64)
    authorized_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    notes: str = Field(default="", max_length=2000)


class ScopeInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    cidr: str
    authorized_until: datetime | None
    enabled: bool
    notes: str
    created_at: datetime


class ScopeList(BaseModel):
    items: list[ScopeInfo] = []


class ScanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_id: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=3, max_length=64)
    ports: list[int] | None = Field(default=None, max_length=50)


class FindingInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    port: int
    service: str
    severity: str
    summary: str


class ScanInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope_id: str
    target: str
    ports: str
    state: str
    findings_count: int
    initiated_by: str | None
    started_at: datetime
    finished_at: datetime | None


class ScanResult(BaseModel):
    scan: ScanInfo
    findings: list[FindingInfo]


class ScanList(BaseModel):
    items: list[ScanInfo] = []


class HardeningItem(BaseModel):
    id: str
    title: str
    status: str
    detail: str


class HardeningList(BaseModel):
    items: list[HardeningItem] = []
