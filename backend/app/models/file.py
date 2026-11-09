"""Content-addressed storage models: blobs, folders, files, versions, favorites."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .user import new_id


class ContentBlob(Base):
    __tablename__ = "content_blobs"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    encrypted_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Folder(TimestampMixin, Base):
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="owner_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", name="parent_id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("owner_id", "parent_id", "name", name="uq_folders_owner_parent_name"),
    )


class File(TimestampMixin, Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="owner_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", name="folder_id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    extension: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    blob_sha256: Mapped[str] = mapped_column(
        ForeignKey("content_blobs.sha256", name="blob_sha256"), nullable=False
    )
    mtime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    blob: Mapped[ContentBlob] = relationship(viewonly=True)


class FileVersion(Base):
    __tablename__ = "file_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", name="file_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    blob_sha256: Mapped[str] = mapped_column(
        ForeignKey("content_blobs.sha256", name="blob_sha256"), nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)  # action slug
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("file_id", "version_number", name="uq_file_versions_file_number"),
        CheckConstraint("version_number > 0", name="file_versions_number_positive"),
    )


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="user_id", ondelete="CASCADE"), primary_key=True
    )
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", name="file_id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
