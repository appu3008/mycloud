"""Quota alert tests: threshold evaluation, dedupe, dismissal."""

from __future__ import annotations

import hashlib

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for


def _upload(client, session, data: bytes, filename: str = "alert.txt") -> dict:
    init = client.post(
        "/api/v1/uploads",
        json={"filename": filename, "size_bytes": len(data),
              "target_folder_id": None, "chunk_size_mb": 1},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert init.status_code == 201, init.text
    upload_id = init.json()["upload_id"]
    for number, chunk in enumerate(chunks_for(data, 1024 * 1024), start=1):
        client.put(
            f"/api/v1/uploads/{upload_id}/chunks/{number}",
            content=chunk,
            headers={
                **csrf_headers(session["csrf_token"]),
                "X-Chunk-Sha256": hashlib.sha256(chunk).hexdigest(),
            },
        )
    done = client.post(
        f"/api/v1/uploads/{upload_id}/complete", json={},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert done.status_code == 200, done.text
    return done.json()


def _set_threshold(client, pct: int) -> str:
    from app.core.database import get_sessionmaker
    from app.models import StorageQuota

    user_id = client.get("/api/v1/auth/me").json()["id"]
    with get_sessionmaker().begin() as db:
        row = db.get(StorageQuota, user_id)
        if row is None:
            db.add(
                StorageQuota(
                    user_id=user_id, quota_bytes=256 * 1024 * 1024,
                    notify_threshold_pct=pct,
                )
            )
        else:
            row.notify_threshold_pct = pct
    return user_id


def test_quota_alert_generated_deduped_and_dismissable(client, admin_auth):
    session = admin_auth
    _set_threshold(client, 0)  # any usage crosses this threshold

    _upload(client, session, b"first")
    status = client.get("/api/v1/alerts").json()
    assert status["triggered"] is True
    assert status["threshold"] == 0
    assert status["percent"] >= 0
    warnings = [n for n in status["notifications"] if n["type"] == "quota_warning"]
    assert len(warnings) == 1
    assert warnings[0]["payload"]["used_bytes"] >= 5
    assert warnings[0]["is_read"] is False

    # More uploads do not spam while the warning is unread.
    _upload(client, session, b"second", filename="second.txt")
    again = client.get("/api/v1/alerts").json()
    assert len([n for n in again["notifications"] if n["type"] == "quota_warning"]) == 1

    dismissed = client.post(
        "/api/v1/alerts/dismiss",
        params={"notification_id": warnings[0]["id"]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert dismissed.status_code == 200
    assert next(n for n in client.get("/api/v1/alerts").json()["notifications"]
                if n["id"] == warnings[0]["id"])["is_read"] is True

    # A fresh warning may be created once the old one is dismissed.
    _upload(client, session, b"third", filename="third.txt")
    latest = client.get("/api/v1/alerts").json()["notifications"]
    assert len([n for n in latest if n["type"] == "quota_warning" and not n["is_read"]]) == 1


def test_no_alert_under_threshold(client, admin_auth):
    session = admin_auth
    _set_threshold(client, 100)
    _upload(client, session, b"tiny")
    status = client.get("/api/v1/alerts").json()
    assert status["triggered"] is False
    assert status["notifications"] == []


def test_alerts_require_auth_and_csrf(client):
    assert client.get("/api/v1/alerts").status_code == 401
    assert client.post("/api/v1/alerts/dismiss", params={"notification_id": "x"}).status_code in (401, 403)
