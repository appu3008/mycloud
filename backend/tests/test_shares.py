"""Share-link tests: creation, listing, revocation, public access rules."""

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


def _mkfolder(client, session, name, parent=None) -> dict:
    response = client.post(
        "/api/v1/folders",
        json={"name": name, "parent_id": parent},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_share(client, session, resource_type, resource_id, **fields) -> dict:
    response = client.post(
        "/api/v1/shares",
        json={"resource_type": resource_type, "resource_id": resource_id, **fields},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- owner endpoints -----------------------------------------------------------


def test_create_share_returns_token_once_and_lists(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"share me", filename="s.txt")
    payload = _create_share(client, session, "file", created["id"])

    assert payload["token"]  # plaintext, only returned here
    assert payload["share"]["resource_name"] == "s.txt"
    assert payload["share"]["password_protected"] is False

    listing = client.get("/api/v1/shares").json()
    assert len(listing["items"]) == 1
    assert listing["items"][0]["id"] == payload["share"]["id"]


def test_create_share_requires_csrf_and_owned_resource(client, admin_auth):
    session = admin_auth
    no_csrf = client.post(
        "/api/v1/shares", json={"resource_type": "file", "resource_id": "x"}
    )
    assert no_csrf.status_code in (401, 403)

    unknown = client.post(
        "/api/v1/shares",
        json={"resource_type": "file", "resource_id": "missing-id"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert unknown.status_code == 404


def test_revoke_share_makes_link_gone(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"revoke me", filename="r.txt")
    payload = _create_share(client, session, "file", created["id"])
    token = payload["token"]

    assert client.get(f"/api/v1/public/shares/{token}").status_code == 200

    revoked = client.delete(
        f"/api/v1/shares/{payload['share']['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert revoked.status_code == 200, revoked.text

    gone = client.get(f"/api/v1/public/shares/{token}")
    assert gone.status_code == 410, gone.text


# --- public endpoints -----------------------------------------------------------


def test_public_download_streams_content_and_counts(client, admin_auth):
    session = admin_auth
    data = b"public bytes"
    created = _upload_file(client, session, data, filename="p.txt")
    token = _create_share(client, session, "file", created["id"])["token"]

    meta = client.get(f"/api/v1/public/shares/{token}")
    assert meta.status_code == 200
    assert meta.json()["kind"] == "file"
    assert meta.json()["name"] == "p.txt"
    assert meta.json()["size_bytes"] == len(data)

    download = client.get(f"/api/v1/public/shares/{token}/download")
    assert download.status_code == 200
    assert download.content == data

    # Download counted on the owner's listing.
    listing = client.get("/api/v1/shares").json()
    assert listing["items"][0]["download_count"] == 1


def test_password_protected_share_rejects_wrong_password(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"locked", filename="l.txt")
    token = _create_share(
        client, session, "file", created["id"], password="open sesame"
    )["token"]

    meta = client.get(f"/api/v1/public/shares/{token}")
    assert meta.json()["has_password"] is True

    missing = client.get(f"/api/v1/public/shares/{token}/download")
    assert missing.status_code == 401

    wrong = client.get(f"/api/v1/public/shares/{token}/download?password=nope")
    assert wrong.status_code == 401

    right = client.get(
        f"/api/v1/public/shares/{token}/download?password=open%20sesame"
    )
    assert right.status_code == 200
    assert right.content == b"locked"


def test_max_downloads_exhausts_share(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"one shot", filename="o.txt")
    token = _create_share(client, session, "file", created["id"], max_downloads=1)[
        "token"
    ]

    first = client.get(f"/api/v1/public/shares/{token}/download")
    assert first.status_code == 200

    second = client.get(f"/api/v1/public/shares/{token}/download")
    assert second.status_code == 410
    assert second.json()["detail"]["error"] == "share_exhausted"


def test_folder_share_lists_and_serves_items(client, admin_auth):
    session = admin_auth
    folder = _mkfolder(client, session, "SharedFolder")
    inner = _upload_file(
        client, session, b"nested share", filename="n.txt", folder=folder["id"]
    )
    token = _create_share(client, session, "folder", folder["id"])["token"]

    meta = client.get(f"/api/v1/public/shares/{token}")
    assert meta.status_code == 200
    assert meta.json()["kind"] == "folder"
    assert meta.json()["name"] == "SharedFolder"

    items = client.get(f"/api/v1/public/shares/{token}/items")
    assert items.status_code == 200
    assert [row["id"] for row in items.json()["items"]] == [inner["id"]]

    download = client.get(f"/api/v1/public/shares/{token}/items/{inner['id']}/download")
    assert download.status_code == 200
    assert download.content == b"nested share"

    # A file outside the folder is not reachable through the share.
    outside = _upload_file(client, session, b"secret", filename="x.txt")
    leak = client.get(
        f"/api/v1/public/shares/{token}/items/{outside['id']}/download"
    )
    assert leak.status_code == 404


def test_share_dies_when_resource_deleted(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"vanish", filename="v.txt")
    token = _create_share(client, session, "file", created["id"])["token"]
    assert client.get(f"/api/v1/public/shares/{token}").status_code == 200

    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [created["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    gone = client.get(f"/api/v1/public/shares/{token}")
    assert gone.status_code == 410
    assert gone.json()["detail"]["error"] == "resource_unavailable"


def test_expired_share_is_gone(client, admin_auth):
    """An expiring link stops working after its deadline."""
    import datetime

    session = admin_auth
    created = _upload_file(client, session, b"brief", filename="b.txt")
    token = _create_share(client, session, "file", created["id"], expires_in_hours=1)[
        "token"
    ]
    assert client.get(f"/api/v1/public/shares/{token}").status_code == 200

    # Shrink the deadline under our feet (SQLite stores naive UTC datetimes).
    import datetime

    from app.core.database import get_sessionmaker
    from app.models import Share
    from app.models.base import utcnow

    with get_sessionmaker().begin() as db:
        row = db.query(Share).first()
        row.expires_at = utcnow() - datetime.timedelta(hours=2)

    gone = client.get(f"/api/v1/public/shares/{token}")
    assert gone.status_code == 410
    assert gone.json()["detail"]["error"] == "share_expired"


def test_unknown_token_404s(client):
    assert client.get("/api/v1/public/shares/nope").status_code == 404
