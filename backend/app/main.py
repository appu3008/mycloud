"""MyCloud API entry point.

Development server binds 127.0.0.1 only (spec rule 9). Public exposure
must go through the reverse proxy/Tailscale setup documented in
docs/DEPLOYMENT.md — never by changing the bind in development.

Run:
    backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .api import auth as auth_api
from .api import activity as activity_api
from .api import analytics as analytics_api
from .api import backups as backups_api
from .api import files as files_api
from .api import folders as folders_api
from .api import public as public_api
from .api import shares as shares_api
from .api import trash as trash_api
from .api import uploads as uploads_api
from .api import versions as versions_api
from .core.config import get_settings
from .core.database import database_status

settings = get_settings()
logger = logging.getLogger("mycloud")

# Disable FastAPI's default docs pages in production.
_docs = {} if settings.is_production else {
    "docs_url": "/api/docs",
    "redoc_url": "/api/redoc",
    "openapi_url": "/api/openapi.json",
}


def create_app() -> FastAPI:
    settings = get_settings()  # fresh: supports test reconfiguration
    app = FastAPI(
        title="MyCloud",
        description="Self-hosted personal cloud storage and device management",
        version="0.1.0",
        **_docs,  # type: ignore[arg-type]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    settings.ensure_runtime_dirs()

    register_routes(app)
    return app


def _disk_usage(path: str) -> dict:
    usage = shutil.disk_usage(path)
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round(usage.used / usage.total * 100, 2) if usage.total else 0,
    }


def register_routes(app: FastAPI) -> None:
    app.include_router(auth_api.router, prefix="/api/v1")
    app.include_router(uploads_api.router, prefix="/api/v1")
    app.include_router(files_api.router, prefix="/api/v1")
    app.include_router(folders_api.router, prefix="/api/v1")
    app.include_router(trash_api.router, prefix="/api/v1")
    app.include_router(analytics_api.router, prefix="/api/v1")
    app.include_router(shares_api.router, prefix="/api/v1")
    app.include_router(public_api.router, prefix="/api/v1")
    app.include_router(activity_api.router, prefix="/api/v1")
    app.include_router(backups_api.router, prefix="/api/v1")
    app.include_router(versions_api.router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def index() -> dict:
        """Friendly root so manual probing points at real paths, not 404s."""
        return {
            "service": "MyCloud API",
            "health": "/api/health",
            "enrollment": "/api/v1/auth/provider/init/status",
            "docs": "/api/docs" if not settings.is_production else None,
        }

    @app.get("/health", include_in_schema=False)
    def health_alias() -> dict:
        """Convenience alias; canonical path is /api/health."""
        return health()

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        """Real health report: storage dirs, disk capacity, database, environment."""
        settings = get_settings()  # read fresh: tests reconfigure env per test
        errors: list[str] = []
        if not settings.files_dir.is_dir():
            errors.append("storage files dir missing")
        if not settings.temporary_dir.is_dir():
            errors.append("storage temporary dir missing")
        if not settings.thumbnails_dir.is_dir():
            errors.append("storage thumbnails dir missing")
        if not settings.secret_key and settings.is_production:
            errors.append("MYCLOUD_SECRET_KEY not set (required in production)")
        if settings.environment == "development" and settings.host != "127.0.0.1":
            errors.append("development server must bind 127.0.0.1")

        return {
            "status": "ok" if not errors else "degraded",
            "environment": settings.environment,
            "storage_root": str(settings.storage_root),
            "disk": _disk_usage(str(settings.storage_root)),
            "database": database_status(),
            "errors": errors,
        }

    @app.get("/api/health/ping", tags=["health"])
    def ping() -> dict:
        return {"ok": True}


app = create_app()
