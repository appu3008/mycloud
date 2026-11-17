"""Recycle bin tests: trash listing, restore, permanent delete (purge)."""

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


def _trash(client):
    response = client.get("/api/v1/trash")
    assert response.status_code == 200, response.text
    return response.json()


# --- listing -----------------------------------------------------------------


def test_delete_file_shows_in_trash_and_restore(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"hello trash", filename="a.txt")
    deleted = client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [created["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert deleted.status_code == 200, deleted.text

    trash = _trash(client)
    assert [row["id"] for row in trash["files"]] == [created["id"]]
    assert trash["files"][0]["deleted_at"] is not None
    assert trash["folders"] == []
    assert trash["total_bytes"] == len(b"hello trash")

    restored = client.post(
        "/api/v1/trash/restore",
        json={"file_ids": [created["id"]], "folder_ids": []},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"]["files"] == 1
    assert _trash(client)["files"] == []

    listing = client.get("/api/v1/files")
    assert created["id"] in [row["id"] for row in listing.json()["items"]]


def test_deleted_folder_hides_inner_files(client, admin_auth):
    """Files inside a deleted folder appear only via the folder row."""
    session = admin_auth
    folder = _mkfolder(client, session, "BinFolder")
    _upload_file(client, session, b"nested", filename="n.txt", folder=folder["id"])

    deleted = client.delete(
        f"/api/v1/folders/{folder['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert deleted.status_code == 200, deleted.text

    trash = _trash(client)
    assert [row["id"] for row in trash["folders"]] == [folder["id"]]
    assert trash["files"] == []  # hidden behind the folder
    # Storage math still counts the nested file.
    assert trash["total_bytes"] == len(b"nested")


def test_restore_deleted_folder_restores_batch(client, admin_auth):
    session = admin_auth
    folder = _mkfolder(client, session, "RestoreMe")
    inner = _upload_file(client, session, b"inner", filename="i.txt", folder=folder["id"])
    assert client.delete(
        f"/api/v1/folders/{folder['id']}",
        headers=csrf_headers(session["csrf_token"]),
    ).status_code == 200

    restored = client.post(
        "/api/v1/trash/restore",
        json={"file_ids": [], "folder_ids": [folder["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"] == {"folders": 1, "files": 1}

    detail = client.get(f"/api/v1/folders/{folder['id']}")
    assert detail.status_code == 200
    listing = client.get(f"/api/v1/files?folder_id={folder['id']}")
    assert inner["id"] in [row["id"] for row in listing.json()["items"]]


def test_restore_file_inside_deleted_folder_conflicts(client, admin_auth):
    session = admin_auth
    folder = _mkfolder(client, session, "Cascade")
    inner = _upload_file(client, session, b"inner", filename="i.txt", folder=folder["id"])
    client.delete(
        f"/api/v1/folders/{folder['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    response = client.post(
        "/api/v1/trash/restore",
        json={"file_ids": [inner["id"]], "folder_ids": []},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 409, response.text


# --- purge -------------------------------------------------------------------


def _purge_file(client, session, file_id, mode="items"):
    return client.post(
        "/api/v1/trash/purge",
        json={"mode": mode, "file_ids": [file_id], "folder_ids": []},
        headers=csrf_headers(session["csrf_token"]),
    )


def test_purge_file_removes_row_and_blob(client, admin_auth, app_env):
    session = admin_auth
    data = b"purge me"
    created = _upload_file(client, session, data, filename="p.txt")
    sha = hashlib.sha256(data).hexdigest()
    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [created["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )

    purged = _purge_file(client, session, created["id"])
    assert purged.status_code == 200, purged.text
    assert purged.json()["purged"] == {"files": 1, "folders": 0,
                                       "bytes_freed": len(data)}
    assert _trash(client)["files"] == []

    # The file is gone for good: restore is a 404 and content 404s too.
    assert client.post(
        "/api/v1/trash/restore",
        json={"file_ids": [created["id"]], "folder_ids": []},
        headers=csrf_headers(session["csrf_token"]),
    ).status_code == 404
    assert client.get(f"/api/v1/files/{created['id']}").status_code == 404

    # Blob bytes physically removed (refcount hit zero).
    from app.core.config import get_settings
    from app.storage.blob_store import blob_abs_path
    assert not blob_abs_path(get_settings(), sha).exists()


def test_purge_dedup_keeps_shared_blob(client, admin_auth, app_env):
    """Two files sharing one blob: purging one keeps the bytes (refcount)."""
    session = admin_auth
    data = b"shared-blob"
    sha = hashlib.sha256(data).hexdigest()
    first = _upload_file(client, session, data, filename="one.txt")
    second = _upload_file(client, session, data, filename="two.txt")
    assert first["size_bytes"] == second["size_bytes"]

    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [first["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    purged = _purge_file(client, session, first["id"])
    assert purged.status_code == 200, purged.text

    from app.core.config import get_settings
    from app.storage.blob_store import blob_abs_path
    assert blob_abs_path(get_settings(), sha).exists()

    # The surviving copy still downloads fine.
    content = client.get(f"/api/v1/files/{second['id']}/content")
    assert content.status_code == 200
    assert content.content == data


def test_purge_all_empties_bin(client, admin_auth):
    session = admin_auth
    folder = _mkfolder(client, session, "Everything")
    _upload_file(client, session, b"inside", filename="i.txt", folder=folder["id"])
    loose = _upload_file(client, session, b"loose", filename="l.txt")

    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [loose["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    client.delete(
        f"/api/v1/folders/{folder['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )

    purged = client.post(
        "/api/v1/trash/purge",
        json={"mode": "all"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert purged.status_code == 200, purged.text
    counts = purged.json()["purged"]
    assert counts["folders"] == 1
    assert counts["files"] == 2  # loose file + nested file
    assert counts["bytes_freed"] == len(b"inside") + len(b"loose")
    assert _trash(client)["files"] == [] and _trash(client)["folders"] == []


def test_purge_requires_csrf_and_unknown_id_404s(client, admin_auth):
    session = admin_auth
    created = _upload_file(client, session, b"secret", filename="s.txt")
    client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [created["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )

    # CSRF enforced.
    no_csrf = client.post("/api/v1/trash/purge", json={"mode": "all"})
    assert no_csrf.status_code in (401, 403), no_csrf.text

    # Unknown/foreign ids resolve to a clean 404, not a crash.
    assert _purge_file(client, session, "nonexistent-id").status_code == 404
