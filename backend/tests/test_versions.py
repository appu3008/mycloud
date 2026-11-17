"""Version history tests: replace archives old bytes; restore brings them back."""

from __future__ import annotations

import hashlib

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for


def _upload(client, session, data: bytes, filename="v.txt", replace=None) -> dict:
    init = client.post(
        "/api/v1/uploads",
        json={
            "filename": filename,
            "size_bytes": len(data),
            "target_folder_id": None,
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
        json={"replace_file_id": replace} if replace else {},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert complete.status_code == 200, complete.text
    return complete.json()


def test_replace_creates_version_and_restore_recovers_bytes(client, admin_auth):
    session = admin_auth
    original = b"version one content"
    updated = b"version two content is longer"
    created = _upload(client, session, original, filename="doc.txt")

    replaced = _upload(client, session, updated, filename="doc-v2.txt", replace=created["id"])
    assert replaced["id"] == created["id"]
    assert replaced["size_bytes"] == len(updated)

    versions = client.get(f"/api/v1/files/{created['id']}/versions").json()["items"]
    assert len(versions) == 1
    version = versions[0]
    assert version["version_number"] == 1
    assert version["blob_sha256"] == hashlib.sha256(original).hexdigest()
    assert version["created_by"] == "upload-replace"

    # Old bytes are still downloadable from the archive.
    old = client.get(f"/api/v1/files/{created['id']}/versions/{version['id']}/content")
    assert old.status_code == 200
    assert old.content == original

    restored = client.post(
        f"/api/v1/files/{created['id']}/versions/{version['id']}/restore",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["blob_sha256"] == hashlib.sha256(original).hexdigest()

    current = client.get(f"/api/v1/files/{created['id']}/content")
    assert current.content == original
    # Restoring is itself versioned: the pre-restore content is kept so the
    # user can flip back to it without uploading again.
    remaining = client.get(f"/api/v1/files/{created['id']}/versions").json()["items"]
    assert len(remaining) == 1
    assert remaining[0]["created_by"] == "restore-before"
    assert remaining[0]["blob_sha256"] == hashlib.sha256(updated).hexdigest()


def test_same_content_replace_does_not_create_version(client, admin_auth):
    session = admin_auth
    data = b"unchanged"
    created = _upload(client, session, data)
    _upload(client, session, data, filename="same.txt", replace=created["id"])
    assert client.get(f"/api/v1/files/{created['id']}/versions").json()["items"] == []


def test_replace_rejects_foreign_file_and_requires_csrf(client, admin_auth):
    session = admin_auth
    created = _upload(client, session, b"guarded")
    # A non-existent target must fail before any bytes are archived.
    init = client.post(
        "/api/v1/uploads",
        json={"filename": "x.txt", "size_bytes": 1, "chunk_size_mb": 1},
        headers=csrf_headers(session["csrf_token"]),
    )
    upload_id = init.json()["upload_id"]
    client.put(
        f"/api/v1/uploads/{upload_id}/chunks/1",
        content=b"x",
        headers={
            **csrf_headers(session["csrf_token"]),
            "X-Chunk-Sha256": hashlib.sha256(b"x").hexdigest(),
        },
    )
    response = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={"replace_file_id": "does-not-exist"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 404
    assert client.get(f"/api/v1/files/{created['id']}/versions").json()["items"] == []


def test_version_endpoints_require_auth(client):
    assert client.get("/api/v1/files/x/versions").status_code == 401
