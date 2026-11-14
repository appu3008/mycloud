"""Phase 5 tests: folder hierarchy, batch operations, ownership scoping."""

from __future__ import annotations

import hashlib
import os

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for

# --- helpers ----------------------------------------------------------------


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


def _mkfolder(client, session, name, parent=None, expect=201):
    response = client.post(
        "/api/v1/folders",
        json={"name": name, "parent_id": parent},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == expect, response.text
    return response.json()


def _file_ids(client, session, folder=None) -> list[str]:
    params = f"?folder_id={folder}" if folder else ""
    listing = client.get(f"/api/v1/files{params}", headers={})
    assert listing.status_code == 200, listing.text
    return [row["id"] for row in listing.json()["items"]]


# --- creation & listing -----------------------------------------------------


def test_create_list_and_breadcrumb(client, admin_auth):
    session = admin_auth
    root = _mkfolder(client, session, "Documents")
    child = _mkfolder(client, session, "Taxes", parent=root["id"])
    assert root["path"] == "Documents"
    assert child["path"] == "Documents/Taxes"

    listing = client.get("/api/v1/folders")
    names = [row["name"] for row in listing.json()["items"]]
    assert names == ["Documents"]

    nested = client.get(f"/api/v1/folders?parent_id={root['id']}")
    assert [row["name"] for row in nested.json()["items"]] == ["Taxes"]

    detail = client.get(f"/api/v1/folders/{child['id']}")
    crumbs = [row["name"] for row in detail.json()["breadcrumb"]]
    assert crumbs == ["Documents", "Taxes"]


def test_duplicate_name_rejected_but_allowed_elsewhere(client, admin_auth):
    session = admin_auth
    a = _mkfolder(client, session, "Reports")
    b = _mkfolder(client, session, "Archive")
    assert _mkfolder(client, session, "Reports", expect=409)  # same parent
    assert _mkfolder(client, session, "Reports", parent=b["id"])  # other parent OK
    assert _mkfolder(client, session, "Archive", parent=a["id"])


def test_invalid_names_rejected(client, admin_auth):
    session = admin_auth
    for bad in ("", "  ", "a/b", "..", "..x", "x\\y", "pad "):
        response = client.post(
            "/api/v1/folders",
            json={"name": bad, "parent_id": None},
            headers=csrf_headers(session["csrf_token"]),
        )
        assert response.status_code == 422, (bad, response.text)


def test_unknown_parent_404(client, admin_auth):
    session = admin_auth
    response = client.post(
        "/api/v1/folders",
        json={"name": "Orphan", "parent_id": "nonexistent0000000000000"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 404, response.text


# --- rename & move ----------------------------------------------------------


def test_rename_updates_descendant_paths(client, admin_auth):
    session = admin_auth
    a = _mkfolder(client, session, "A")
    b = _mkfolder(client, session, "B", parent=a["id"])
    renamed = client.patch(
        f"/api/v1/folders/{a['id']}",
        json={"name": "Alpha"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["path"] == "Alpha"
    child = client.get(f"/api/v1/folders/{b['id']}")
    assert child.json()["path"] == "Alpha/B"


def test_rename_conflict_409(client, admin_auth):
    session = admin_auth
    _mkfolder(client, session, "One")
    two = _mkfolder(client, session, "Two")
    response = client.patch(
        f"/api/v1/folders/{two['id']}",
        json={"name": "One"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 409, response.text


def test_move_rewrites_paths_and_rejects_cycles(client, admin_auth):
    session = admin_auth
    a = _mkfolder(client, session, "A")
    b = _mkfolder(client, session, "B", parent=a["id"])
    c = _mkfolder(client, session, "C", parent=b["id"])

    # A into its own descendant -> cycle
    into_child = client.post(
        f"/api/v1/folders/{a['id']}/move",
        json={"parent_id": b["id"]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert into_child.status_code == 400, into_child.text
    assert into_child.json()["detail"]["error"] == "folder_cycle"

    # B to root: paths of B and C rewritten
    moved = client.post(
        f"/api/v1/folders/{b['id']}/move",
        json={"parent_id": None},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["path"] == "B"
    c_detail = client.get(f"/api/v1/folders/{c['id']}")
    assert c_detail.json()["path"] == "B/C"


def test_move_conflict_409(client, admin_auth):
    session = admin_auth
    parent = _mkfolder(client, session, "Parent")
    _mkfolder(client, session, "Existing", parent=parent["id"])
    other = _mkfolder(client, session, "Existing")  # root sibling, fine
    response = client.post(
        f"/api/v1/folders/{other['id']}/move",
        json={"parent_id": parent["id"]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 409, response.text


# --- recursive delete & restore ---------------------------------------------


def test_recursive_delete_and_restore(client, admin_auth):
    session = admin_auth
    root = _mkfolder(client, session, "Project")
    sub = _mkfolder(client, session, "Drafts", parent=root["id"])
    kept_outside = _mkfolder(client, session, "Safe")

    inside_root = _upload_file(client, session, b"a" * 10, "in-root.txt", folder=root["id"])
    inside_sub = _upload_file(client, session, b"b" * 10, "in-sub.txt", folder=sub["id"])
    outside = _upload_file(client, session, b"c" * 10, "outside.txt")
    # Individually delete one file BEFORE the folder cascade.
    solo = _upload_file(client, session, b"d" * 10, "solo.txt", folder=root["id"])
    deleted_solo = client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [solo["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert deleted_solo.status_code == 200, deleted_solo.text

    removed = client.delete(
        f"/api/v1/folders/{root['id']}", headers=csrf_headers(session["csrf_token"])
    )
    assert removed.status_code == 200, removed.text
    counts = removed.json()["deleted"]
    assert counts == {"folders": 2, "files": 2}  # solo.txt already deleted

    # Listing no longer shows the folder; its files are gone from views.
    listing = client.get("/api/v1/folders")
    assert kept_outside["id"] in [row["id"] for row in listing.json()["items"]]
    assert root["id"] not in [row["id"] for row in listing.json()["items"]]
    assert _file_ids(client, session) == [outside["id"]]

    # Deleted folder itself 404s for reads.
    assert client.get(f"/api/v1/folders/{root['id']}").status_code == 404

    # Restore brings back exactly the cascade batch (not solo.txt).
    restored = client.post(
        f"/api/v1/folders/{root['id']}/restore",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"] == {"folders": 2, "files": 2}
    root_files = _file_ids(client, session, root["id"])
    assert inside_root["id"] in root_files
    assert inside_sub["id"] in _file_ids(client, session, sub["id"])
    assert outside["id"] in _file_ids(client, session)  # untouched by the cascade
    assert solo["id"] not in root_files  # stays in the recycle bin
    assert client.get(f"/api/v1/folders/{sub['id']}").json()["path"] == "Project/Drafts"


def test_restore_active_folder_conflicts(client, admin_auth):
    session = admin_auth
    root = _mkfolder(client, session, "Alive")
    response = client.post(
        f"/api/v1/folders/{root['id']}/restore",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 409, response.text


def test_folder_tree_shape(client, admin_auth):
    session = admin_auth
    a = _mkfolder(client, session, "A")
    _mkfolder(client, session, "A1", parent=a["id"])
    tree = client.get("/api/v1/folders/tree")
    assert tree.status_code == 200, tree.text
    (node,) = tree.json()
    assert node["name"] == "A"
    assert [child["name"] for child in node["children"]] == ["A1"]


# --- batch file operations --------------------------------------------------


def test_batch_move_copy_favorite_delete_restore(client, admin_auth):
    session = admin_auth
    target = _mkfolder(client, session, "Target")
    file1 = _upload_file(client, session, b"one", "one.txt")
    file2 = _upload_file(client, session, b"two", "two.txt")

    moved = client.post(
        "/api/v1/files/batch",
        json={"action": "move", "file_ids": [file1["id"], file2["id"]],
              "target_folder_id": target["id"]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json() == {"updated": 2}
    assert _file_ids(client, session, target["id"]) == [file1["id"], file2["id"]]

    copied = client.post(
        "/api/v1/files/batch",
        json={"action": "copy", "file_ids": [file1["id"]],
              "target_folder_id": None},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert copied.status_code == 200, copied.text
    root_listing = client.get("/api/v1/files")
    root_names = [row["name"] for row in root_listing.json()["items"]]
    assert root_names == ["one (copy).txt"]

    # Copy inside same folder: names stay unique.
    copied2 = client.post(
        "/api/v1/files/batch",
        json={"action": "copy", "file_ids": [file1["id"]],
              "target_folder_id": target["id"]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert copied2.status_code == 200, copied2.text
    target_names = [
        row["name"] for row in client.get(f"/api/v1/files?folder_id={target['id']}").json()["items"]
    ]
    # Listing sorts by name; space sorts before dot, so the copy comes first.
    assert target_names == ["one (copy).txt", "one.txt", "two.txt"]

    fav = client.post(
        "/api/v1/files/batch",
        json={"action": "favorite", "file_ids": [file1["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert fav.status_code == 200, fav.text
    meta = client.get(f"/api/v1/files/{file1['id']}")
    assert meta.json()["is_favorite"] is True

    wiped = client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": [file1["id"], file2["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert wiped.status_code == 200, wiped.text
    # The earlier copy ("one (copy).txt") is its own row: it must survive.
    target_names = [
        row["name"] for row in client.get(f"/api/v1/files?folder_id={target['id']}").json()["items"]
    ]
    assert target_names == ["one (copy).txt"]

    brought_back = client.post(
        "/api/v1/files/batch",
        json={"action": "restore", "file_ids": [file2["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert brought_back.status_code == 200, brought_back.text
    target_names = [
        row["name"] for row in client.get(f"/api/v1/files?folder_id={target['id']}").json()["items"]
    ]
    assert target_names == ["one (copy).txt", "two.txt"]


def test_batch_unknown_file_404(client, admin_auth):
    session = admin_auth
    response = client.post(
        "/api/v1/files/batch",
        json={"action": "delete", "file_ids": ["nonexistent000000000000"]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 404, response.text


def test_batch_copy_quota_enforced(client, admin_auth):
    """Copy must respect the same quota math as uploads."""
    session = admin_auth
    payload = os.urandom(256 * 1024)
    file1 = _upload_file(client, session, payload, "big.bin")
    # Default test quota is 256 MiB; make one copy OK, then shrink room by
    # checking the guard exists: copy repeatedly until quota trips.
    statuses = []
    for _ in range(1200):
        response = client.post(
            "/api/v1/files/batch",
            json={"action": "copy", "file_ids": [file1["id"]]},
            headers=csrf_headers(session["csrf_token"]),
        )
        statuses.append(response.status_code)
        if response.status_code != 200:
            assert response.status_code == 413, response.text
            assert response.json()["detail"]["error"] == "quota_exceeded"
            break
    assert 413 in statuses, "expected quota to trip on repeated copies"


def test_file_rename_endpoint(client, admin_auth):
    session = admin_auth
    file1 = _upload_file(client, session, b"hello", "hello.txt")
    renamed = client.patch(
        f"/api/v1/files/{file1['id']}",
        json={"name": "greetings.md"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert body["name"] == "greetings.md"
    assert body["extension"] == "md"

    bad = client.patch(
        f"/api/v1/files/{file1['id']}",
        json={"name": "a/b"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert bad.status_code == 422, bad.text


def test_move_file_unknown_target_404(client, admin_auth):
    session = admin_auth
    file1 = _upload_file(client, session, b"x", "x.txt")
    response = client.post(
        "/api/v1/files/batch",
        json={"action": "move", "file_ids": [file1["id"]],
              "target_folder_id": "nonexistent0000000000000"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 404, response.text


# --- ownership scoping --------------------------------------------------------


def test_folder_ops_require_auth(client, admin_auth):
    """IDOR guard: every folder op 401s without a session."""
    session = admin_auth
    root = _mkfolder(client, session, "Private")

    from fastapi.testclient import TestClient

    intruder = TestClient(client.app)
    assert intruder.get("/api/v1/folders").status_code == 401
    assert intruder.get("/api/v1/folders/tree").status_code == 401
    assert intruder.post(
        "/api/v1/folders", json={"name": "X", "parent_id": None}
    ).status_code in (401, 403)
    assert intruder.patch(
        f"/api/v1/folders/{root['id']}", json={"name": "Stolen"}
    ).status_code in (401, 403)
    assert intruder.delete(f"/api/v1/folders/{root['id']}").status_code in (401, 403)


def test_folder_csrf_required(client, admin_auth):
    response = client.post("/api/v1/folders", json={"name": "NoCsrf", "parent_id": None})
    assert response.status_code == 403, response.text
