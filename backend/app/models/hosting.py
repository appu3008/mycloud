"""Hosted apps and authorized network-audit models (phases 18/19)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, utcnow
from .user import new_id


class HostedApp(Base, TimestampMixin):
    """One app/site served by the local nginx instance.

    ``kind=static`` serves files under root_path; ``kind=proxy`` forwards to
    an upstream port on loopback. The generated nginx config lives in the
    user-owned staging dir until an operator applies it with sudo.
    """

    __tablename__ = "hosted_apps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    path_prefix: Mapped[str] = mapped_column(String(255), nullable=False, default="/")
    upstream_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    root_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    __table_args__ = (
        CheckConstraint("kind IN ('static','proxy')", name="hosted_apps_kind_valid"),
    )


class ScanScope(Base):
    """Written authorization to audit a private network segment."""

    __tablename__ = "scan_scopes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cidr: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="owner_user_id", ondelete="CASCADE"), nullable=False
    )
    authorized_until: Mapped[datetime | None] = mapped_column(nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)


class NetworkScan(Base):
    """One port scan against a target inside an authorized scope."""

    __tablename__ = "network_scans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope_id: Mapped[str] = mapped_column(
        ForeignKey("scan_scopes.id", name="scope_id", ondelete="CASCADE"), nullable=False
    )
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    ports: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    initiated_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="initiated_by", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ScanFinding(Base):
    """One open port found by a scan (never credentials or exploit payloads)."""

    __tablename__ = "scan_findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(
        ForeignKey("network_scans.id", name="scan_id", ondelete="CASCADE"), nullable=False
    )
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    service: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
