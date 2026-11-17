"""Consolidated security regression suite.

Focuses on cross-cutting guarantees across the newer subsystems: hashed
secrets at rest, RBAC, CSRF on every mutating route, ownership isolation and
untrusted input treated as data. Endpoint-specific happy paths live in their
own test modules; this suite checks the security invariants hold everywhere.
"""

from __future__ import annotations

import hashlib
import hmac

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for


def _upload(client, session, data: bytes, filename: str = "sec.txt") -> dict:
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


def _second_user(client) -> dict:
    """Create a non-admin user and return a fresh session dict."""
    from app.core.database import get_sessionmaker
    from app.models import User, new_id, utcnow
    from app.security.password import hash_password

    with get_sessionmaker().begin() as db:
        db.add(
            User(
                id=new_id(), email="other@example.com", display_name="Other",
                password_hash=hash_password("other-pass-9"), role="user",
                is_admin=False, is_active=True, created_at=utcnow(), updated_at=utcnow(),
            )
        )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.com", "password": "other-pass-9"},
    )
    assert login.status_code == 200, login.text
    return {
        "cookies": dict(client.cookies),
        "csrf_token": login.json()["csrf_token"],
        "email": "other@example.com",
    }


def _switch(client, session: dict) -> None:
    client.cookies.clear()
    client.cookies.update(session["cookies"])


# --- secrets at rest --------------------------------------------------------------


def test_session_token_stored_hashed_only(client, admin_auth):
    from app.core.database import get_sessionmaker
    from app.models import Session as SessionRow

    raw = admin_auth["cookies"]["mycloud_session"]
    with get_sessionmaker()() as db:
        rows = db.query(SessionRow).all()
        stored = [row.id for row in rows]
    digest = hashlib.sha256(raw.encode()).hexdigest()
    assert digest in stored
    assert all(not hmac.compare_digest(raw, value) for value in stored)


def test_share_token_stored_hashed_only(client, admin_auth):
    from app.core.database import get_sessionmaker
    from app.models import Share

    session = admin_auth
    file_row = _upload(client, session, b"hash me")
    created = client.post(
        "/api/v1/shares",
        json={"resource_type": "file", "resource_id": file_row["id"]},
        headers=csrf_headers(session["csrf_token"]),
    ).json()
    token = created["token"]
    with get_sessionmaker()() as db:
        hashes = [row.token_hash for row in db.query(Share).all()]
    assert hashlib.sha256(token.encode()).hexdigest() in hashes
    assert token not in hashes


def test_password_hash_is_argon2id_and_verifies(client, admin_auth):
    from app.core.database import get_sessionmaker
    from app.models import User
    from app.security.password import verify_password

    with get_sessionmaker()() as db:
        row = db.query(User).filter(User.id == client.get("/api/v1/auth/me").json()["id"]).one()
        stored = row.password_hash
    assert stored.startswith("$argon2id$")
    assert verify_password(admin_auth["password"], stored)
    assert not verify_password("wrong-password", stored)


# --- RBAC + CSRF on every newer mutation surface ---------------------------------


def test_all_new_mutations_require_csrf(client, admin_auth):
    session = admin_auth
    calls = [
        ("/api/v1/albums", "POST", {"name": "x"}),
        ("/api/v1/devices", "POST", {"name": "x", "platform": "android"}),
        ("/api/v1/alerts/dismiss?notification_id=nope", "POST", {}),
        ("/api/v1/backups/jobs", "POST", {"name": "x"}),
        ("/api/v1/admin/users/x", "PATCH", {"is_admin": True}),
        ("/api/v1/sync/jobs", "POST", {"device_id": "x", "file_id": "y", "direction": "up"}),
        ("/api/v1/files/x/versions/y/restore", "POST", {}),
    ]
    for path, method, body in calls:
        response = client.request(method, path, json=body)
        assert response.status_code in (401, 403), (path, response.status_code)


def test_non_admin_cannot_use_admin_or_backup_apis(client, admin_auth):
    admin = admin_auth
    _upload(client, admin, b"owned by admin")
    other = _second_user(client)
    _switch(client, other)

    assert client.get("/api/v1/admin/overview").status_code == 403
    assert client.get("/api/v1/backups/jobs").status_code == 403
    assert client.post(
        "/api/v1/backups/jobs",
        json={"name": "attack"},
        headers=csrf_headers(other["csrf_token"]),
    ).status_code == 403


# --- ownership isolation across new subsystems ------------------------------------


def test_other_user_cannot_reach_admin_file_through_new_endpoints(client, admin_auth):
    admin = admin_auth
    file_row = _upload(client, admin, b"private")

    album = client.post(
        "/api/v1/albums", json={"name": "Mine"},
        headers=csrf_headers(admin["csrf_token"]),
    ).json()

    other = _second_user(client)
    _switch(client, other)

    assert client.get(f"/api/v1/files/{file_row['id']}/versions").status_code == 404
    assert client.get(f"/api/v1/media/{file_row['id']}/thumbnail").status_code == 404
    assert client.get(f"/api/v1/media/photos?album_id={album['id']}").status_code == 404
    assert client.post(
        f"/api/v1/albums/{album['id']}/files",
        json={"file_ids": [file_row["id"]]},
        headers=csrf_headers(other["csrf_token"]),
    ).status_code == 404
    assert client.get(f"/api/v1/devices/{album['id']}/backup-config").status_code == 404


def test_other_user_cannot_restore_or_issue_share_for_file(client, admin_auth):
    admin = admin_auth
    file_row = _upload(client, admin, b"secret")
    other = _second_user(client)
    _switch(client, other)

    assert client.post(
        "/api/v1/shares",
        json={"resource_type": "file", "resource_id": file_row["id"]},
        headers=csrf_headers(other["csrf_token"]),
    ).status_code == 404
    assert client.post(
        f"/api/v1/files/{file_row['id']}/versions/nope/restore",
        headers=csrf_headers(other["csrf_token"]),
    ).status_code == 404


# --- untrusted input is data, never code ------------------------------------------


def test_injection_like_names_are_stored_as_literal_data(client, admin_auth):
    """SQL/HTML-looking strings are names, not code (Yew escapes on render)."""
    session = admin_auth
    hostile = "'; DROP TABLE files; --<script>alert(1)"
    file_row = _upload(client, session, b"literal data", filename=hostile[:200])
    # The filesystem-facing sanitizer strips path separators and control chars;
    # the DB stores a plain string, never interprets it.
    assert "DROP TABLE" in file_row["name"]
    assert client.get("/api/v1/files").status_code == 200
    assert any(row["id"] == file_row["id"] for row in client.get("/api/v1/files").json()["items"])

    album = client.post(
        "/api/v1/albums", json={"name": hostile[:128]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert album.status_code == 201, album.text
    assert album.json()["name"] == hostile[:128]

    # Paths in names never escape the blob store: content remains addressable
    # by SHA-256, not by the filename.
    download = client.get(f"/api/v1/files/{file_row['id']}/content")
    assert download.content == b"literal data"


def test_revoked_share_and_unknown_token_are_unavailable(client, admin_auth):
    session = admin_auth
    file_row = _upload(client, session, b"revoked")
    created = client.post(
        "/api/v1/shares",
        json={"resource_type": "file", "resource_id": file_row["id"]},
        headers=csrf_headers(session["csrf_token"]),
    ).json()
    token = created["token"]
    assert client.get(f"/api/v1/public/shares/{token}").status_code == 200

    client.delete(
        f"/api/v1/shares/{created['share']['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert client.get(f"/api/v1/public/shares/{token}").status_code == 410
    assert client.get("/api/v1/public/shares/not-a-real-token").status_code == 404
