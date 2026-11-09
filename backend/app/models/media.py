"""Sharing, albums, media metadata models."""

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


class Share(Base):
    __tablename__ = "shares"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="owner_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", name="file_id", ondelete="CASCADE"), nullable=True
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", name="folder_id", ondelete="CASCADE"), nullable=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="download")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(file_id IS NOT NULL OR folder_id IS NOT NULL)", name="share_resource_present"
        ),
        CheckConstraint("mode IN ('download','readonly','upload')", name="share_mode_valid"),
        CheckConstraint("download_count >= 0", name="share_download_count_nonnegative"),
    )


class Album(TimestampMixin, Base):
    __tablename__ = "albums"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="owner_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    cover_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", name="cover_file_id", ondelete="SET NULL"), nullable=True
    )

    files: Mapped[list[AlbumFile]] = relationship(
        back_populates="album", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_albums_owner_name"),)


class AlbumFile(Base):
    __tablename__ = "album_files"

    album_id: Mapped[str] = mapped_column(
        ForeignKey("albums.id", name="album_id", ondelete="CASCADE"), primary_key=True
    )
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", name="file_id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    album: Mapped[Album] = relationship(back_populates="files")


class MediaMetadata(Base):
    __tablename__ = "media_metadata"

    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", name="file_id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Integer, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    exif_json: Mapped[str] = mapped_column(String(4096), nullable=False, default="{}")
    gps_stripped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (CheckConstraint("kind IN ('photo','video')", name="media_kind_valid"),)
