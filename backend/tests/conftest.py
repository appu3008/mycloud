"""Shared pytest fixtures: fully isolated per-test environment.

Each test gets its own temp database/storage/data dir, fresh cached settings,
and a rebuilt engine+app. Nothing here touches the real project database.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def app_env(tmp_path: Path):
    env = {
        "MYCLOUD_DATABASE_URL": f"sqlite:///{tmp_path}/test.db",
        "MYCLOUD_STORAGE_ROOT": str(tmp_path / "storage"),
        "MYCLOUD_DATA_DIR": str(tmp_path / "data"),
        "MYCLOUD_SECRET_KEY": "test-secret-rotate-me-0123456789abcdef",
        "MYCLOUD_ENVIRONMENT": "development",
        "MYCLOUD_LOGIN_MAX_FAILED_ATTEMPTS": "3",
        "MYCLOUD_LOGIN_ATTEMPT_WINDOW_MINUTES": "15",
        "MYCLOUD_LOGIN_LOCKOUT_MINUTES": "15",
        "MYCLOUD_SESSION_TTL_HOURS": "168",
        "MYCLOUD_SESSION_ABSOLUTE_TTL_HOURS": "2160",
        # Test temp dirs often sit on a small tmpfs; keep real guardrails
        # for production envs but relax thresholds so tests exercise logic.
        "MYCLOUD_MIN_FREE_SPACE_MB": "64",
        "MYCLOUD_DISK_USAGE_LIMIT_PCT": "99",
        "MYCLOUD_DEFAULT_QUOTA_MB": "256",
    }
    os.environ.update(env)
    _reset_cached_state()
    from app.core.database import get_engine
    from app.main import create_app
    from app.models import Base

    app = create_app()
    Base.metadata.create_all(get_engine())  # tests: models==migration DDL
    app.state.test_tmp = tmp_path
    yield app
    for key in env:
        os.environ.pop(key, None)
    _reset_cached_state()


@pytest.fixture()
def client(app_env):
    from fastapi.testclient import TestClient

    return TestClient(app_env)


def _reset_cached_state() -> None:
    from app.core import database
    from app.core.config import get_settings

    get_settings.cache_clear()
    database._engine = None
    database._sessionmaker = None


# --- shared login/enrollment helpers ---------------------------------------


@pytest.fixture()
def admin_auth(client):
    """Enroll the first admin and return (cookies dict, csrf_token, body)."""
    enroll = client.post(
        "/api/v1/auth/provider/init",
        json={
            "email": "root@example.com",
            "display_name": "Root",
            "password": "correct-horse-9",
        },
    )
    assert enroll.status_code == 201, enroll.text
    csrf = enroll.json()["csrf_token"]
    return {
        "cookies": dict(client.cookies),
        "csrf_token": csrf,
        "email": "root@example.com",
        "password": "correct-horse-9",
    }


def csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}
