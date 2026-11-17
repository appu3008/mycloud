"""Storage analytics tests: usage snapshot + exact-duplicate detection."""

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


def test_usage_counts_live_files_and_quota(client, admin_auth):
    session = admin_auth
    _upload_file(client, session, b"usage-one", filename="one.txt")
    _upload_file(client, session, b"usage-two!", filename="two.txt")

    response = client.get("/api/v1/storage/usage")
    assert response.status_code == 200, response.text
    usage = response.json()
    assert usage["file_count"] == 2
    assert usage["used_bytes"] == len(b"usage-one") + len(b"usage-two!")
    assert usage["quota_bytes"] > 0
    assert usage["trash_files"] == 0


def test_usage_counts_trash_separately(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"doomed", filename="doomed.txt")
    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [created["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )

    usage = client.get("/api/v1/storage/usage").json()
    assert usage["file_count"] == 0
    assert usage["used_bytes"] == 0  # deleted files are not live usage
    assert usage["trash_files"] == 1
    assert usage["trash_bytes"] == len(b"doomed")


def test_duplicates_finds_shared_content(client, admin_auth):
    session = admin_auth
    data = b"identical-content"
    first = _upload_file(client, session, data, filename="one.txt")
    second = _upload_file(client, session, data, filename="copy-of-one.txt")
    unique = _upload_file(client, session, b"one-of-a-kind", filename="unique.txt")

    response = client.get("/api/v1/duplicates")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["group_count"] == 1
    assert report["total_wasted_bytes"] == len(data)  # one redundant copy
    group = report["groups"][0]
    ids = [item["id"] for item in group["items"]]
    assert first["id"] in ids and second["id"] in ids
    assert unique["id"] not in ids
    assert group["copies"] == 2
    assert group["size_bytes"] == len(data)


def test_duplicates_empty_when_all_content_unique(client, admin_auth):
    session = admin_auth
    _upload_file(client, session, b"alpha", filename="a.txt")
    _upload_file(client, session, b"beta", filename="b.txt")

    report = client.get("/api/v1/duplicates").json()
    assert report["groups"] == []
    assert report["group_count"] == 0
    assert report["total_wasted_bytes"] == 0


def test_duplicates_ignore_deleted_copies(client, admin_auth):
    """One copy in the bin: nothing is wasted among live files."""
    session = admin_auth
    data = b"twin-files"
    first = _upload_file(client, session, data, filename="one.txt")
    _upload_file(client, session, data, filename="two.txt")
    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [first["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )

    report = client.get("/api/v1/duplicates").json()
    assert report["groups"] == []


def test_analytics_require_auth(client):
    assert client.get("/api/v1/storage/usage").status_code == 401
    assert client.get("/api/v1/duplicates").status_code == 401
