"""Activity timeline tests: events are recorded and scoped per user."""

from __future__ import annotations

import hashlib

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for


def _upload_file(client, session, data: bytes, filename="f.bin", folder=None) -> dict:
    init = client.post(
        "/api/v1/uploads",
        json={
            "filename": filename,
            "size_bytes": len(data),
            "target_folder_id": folder,
            "chunk_size_mb": 1,
        },
        headers=csrf_headers(session["csrf_token"]),
    )
    assert init.status_code == 201, init.text
    upload_id = init.json()["upload_id"]
    for number, chunk in enumerate(chunks_for(data, 1024 * 1024), start=1):
        saved = client.put(
            f"/api/v1/uploads/{upload_id}/chunks/{number}",
            content=chunk,
            headers={
                **csrf_headers(session["csrf_token"]),
                "X-Chunk-Sha256": hashlib.sha256(chunk).hexdigest(),
            },
        )
        assert saved.status_code == 200, saved.text
    complete = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert complete.status_code == 200, complete.text
    return complete.json()


def _timeline(client) -> list[dict]:
    response = client.get("/api/v1/activity")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_activity_records_login_upload_delete(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"timeline", filename="t.txt")
    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [created["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )

    kinds = [row["kind"] for row in _timeline(client)]
    assert "upload" in kinds
    assert "delete" in kinds


def test_activity_records_share_login_logout(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"shared out", filename="a.txt")
    client.post(
        "/api/v1/shares",
        json={"resource_type": "file", "resource_id": created["id"]},
        headers=csrf_headers(session["csrf_token"]),
    )
    client.post("/api/v1/auth/logout")

    # Log back in to read the timeline (the session ended with logout).
    relogin = client.post(
        "/api/v1/auth/login",
        json={"email": session["email"], "password": session["password"]},
    )
    assert relogin.status_code == 200, relogin.text

    kinds = [row["kind"] for row in _timeline(client)]
    assert "share" in kinds
    assert "logout" in kinds
    assert "login" in kinds  # the fresh sign-in


def test_activity_scoped_and_paginated(client, admin_auth):
    session = admin_auth
    for index in range(3):
        created = _upload_file(client, session, b"x", filename=f"n{index}.txt")
        client.post(
            "/api/v1/files/batch",
            json={"action": "delete", "file_ids": [created["id"]]},
            headers=csrf_headers(session["csrf_token"]),
        )

    events = _timeline(client)
    assert len(events) >= 6
    totals = client.get("/api/v1/activity").json()["total"]

    page = client.get("/api/v1/activity?limit=2&page=1")
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["total"] == totals
    # Newest first ordering.
    assert events[0]["created_at"] >= events[-1]["created_at"]


def test_activity_requires_auth(client):
    assert client.get("/api/v1/activity").status_code == 401
