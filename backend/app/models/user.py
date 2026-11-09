"""User, storage quota and notification models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


def new_id() -> str:
    return uuid.uuid4().hex


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('admin','user')", name="user_role_valid"),
    )


class StorageQuota(Base):
    __tablename__ = "storage_quotas"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="user_id", ondelete="CASCADE"), primary_key=True
    )
    quota_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notify_threshold_pct: Mapped[int] = mapped_column(INTEGER, nullable=False, default=85)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    user: Mapped[User] = relationship(viewonly=True)
