"""Chunked upload pipeline models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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

UPLOAD_STATES = ("reserved", "uploading", "assembling", "complete", "failed", "aborted")


class Upload(TimestampMixin, Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", name="target_folder_id", ondelete="CASCADE"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    received_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved", index=True)
    final_blob_sha256: Mapped[str | None] = mapped_column(
        ForeignKey("content_blobs.sha256", name="final_blob_sha256"), nullable=True
    )
    final_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_upload_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    chunks: Mapped[list["UploadChunk"]] = relationship(  # noqa: F821
        back_populates="upload", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "client_upload_id", name="uq_uploads_user_client_id"),
        CheckConstraint("total_chunks > 0", name="uploads_total_chunks_positive"),
        CheckConstraint("received_chunks >= 0", name="uploads_received_nonnegative"),
        CheckConstraint("state IN ('reserved','uploading','assembling','complete',"
                        "'failed','aborted')", name="uploads_state_valid"),
    )


class UploadChunk(Base):
    __tablename__ = "upload_chunks"

    upload_id: Mapped[str] = mapped_column(
        ForeignKey("uploads.id", name="upload_id", ondelete="CASCADE"), primary_key=True
    )
    chunk_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    upload: Mapped[Upload] = relationship(back_populates="chunks")
