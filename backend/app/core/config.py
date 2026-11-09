"""Typed application settings.

All values come from environment variables with the MYCLOUD_ prefix
(read from project root .env when present). No hardcoded credentials:
secret_key MUST be provided via .env (scripts/generate_secret.py).

Database portability: DATABASE_URL is the only provider-specific value.
Changing it to a postgresql:// URL later is the intended migration path
(spec section 3); every other module uses the session factory/config only.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Project root = parent of backend/
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYCLOUD_",
        env_file=(str(PROJECT_ROOT / ".env"),),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    environment: str = "development"
    log_level: str = "INFO"

    # --- Server binding ---
    host: str = "127.0.0.1"
    port: int = 8000

    # --- Paths & database ---
    storage_root: Path = PROJECT_ROOT / "storage"
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'database' / 'mycloud.db'}"

    # --- Security ---
    secret_key: str = ""
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173"]
    )
    cookie_secure: bool = False

    # --- Sessions ---
    session_ttl_hours: int = 168            # idle timeout (7 days)
    session_absolute_ttl_hours: int = 2160  # absolute timeout (90 days)

    # --- Uploads ---
    upload_chunk_size_mb: int = 8
    max_file_size_mb: int = 2048

    # --- Storage guardrails ---
    disk_usage_limit_pct: int = 85
    min_free_space_mb: int = 30720

    # --- Quotas ---
    default_quota_mb: int = 20480

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> list[str] | object:
        # Env value may be JSON (["..",".."]) or comma separated ("a,b").
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("secret_key")
    @classmethod
    def _warn_if_missing(cls, value: str) -> str:
        # Not fatal here (Phase 1 has no auth routes yet); enforced later
        # by the security layer before any login succeeds.
        return value

    @field_validator("storage_root")
    @classmethod
    def _resolve_relative_paths(cls, value: Path) -> Path:
        # ".env may specify paths relative to the project root; resolve them
        # against PROJECT_ROOT so behavior is independent of the CWD.
        return value if value.is_absolute() else (PROJECT_ROOT / value)

    @field_validator("database_url")
    @classmethod
    def _resolve_relative_database_url(cls, value: str) -> str:
        # sqlite:///relative/path.db must also be project-root anchored.
        prefix = "sqlite:///"
        if value.startswith(prefix) and not value[len(prefix):].startswith("/"):
            return f"{prefix}{PROJECT_ROOT / value[len(prefix):]}"
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def files_dir(self) -> Path:
        return self.storage_root / "files"

    @property
    def thumbnails_dir(self) -> Path:
        return self.storage_root / "thumbnails"

    @property
    def temporary_dir(self) -> Path:
        return self.storage_root / "temporary"

    def ensure_runtime_dirs(self) -> None:
        """Create storage/database directories if missing (safe, idempotent)."""
        for path in (
            self.files_dir,
            self.thumbnails_dir,
            self.temporary_dir,
            (PROJECT_ROOT / "database"),
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
