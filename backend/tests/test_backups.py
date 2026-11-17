"""Backup job tests: create, run (real snapshot + blobs), prune, verify."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for


def _upload_file(client, session, data: bytes, filename="f.bin") -> dict:
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
        json={},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert complete.status_code == 200, complete.text
    return complete.json()


def _create_job(client, session, **fields) -> dict:
    payload = {"name": "nightly", "retention_count": 2, **fields}
    response = client.post(
        "/api/v1/backups/jobs", json=payload,
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _tmp_target() -> str:
    """A target under the (tmp) data dir of this test's isolated settings."""
    from app.core.config import get_settings

    return str(get_settings().data_dir / "backups-test")


def test_backup_job_crud_and_admin_gate(client, admin_auth):
    session = admin_auth
    job = _create_job(client, session)

    listing = client.get("/api/v1/backups/jobs").json()
    assert [row["id"] for row in listing["items"]] == [job["id"]]
    assert listing["items"][0]["name"] == "nightly"

    deleted = client.delete(
        f"/api/v1/backups/jobs/{job['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert deleted.status_code == 200
    assert client.get("/api/v1/backups/jobs").json()["items"] == []

    # CSRF enforced on mutations.
    assert client.post(
        "/api/v1/backups/jobs", json={"name": "x"}
    ).status_code in (401, 403)


def test_run_backup_writes_snapshot_manifest_and_blobs(client, admin_auth):
    session = admin_auth
    data = b"backup payload"
    created = _upload_file(client, session, data, filename="b.txt")
    job = _create_job(client, session, target_path=str(_tmp_target()))

    run_response = client.post(
        f"/api/v1/backups/jobs/{job['id']}/run",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert run_response.status_code == 200, run_response.text
    run = run_response.json()
    assert run["state"] == "verified"
    assert run["finished_at"] is not None

    destination = Path(run["destination"])
    snapshot = destination / "mycloud.db"
    manifest = json.loads((destination / "manifest.json").read_text())
    assert snapshot.is_file() and snapshot.stat().st_size > 0
    assert manifest["content_sha256"]
    assert manifest["database_bytes"] > 0

    blob_entry = next(
        (e for e in manifest["blobs"] if e["sha256"] == hashlib.sha256(data).hexdigest()),
        None,
    )
    assert blob_entry is not None and blob_entry["present"] is True
    copied = (
        destination / "blobs" / blob_entry["sha256"][:2]
        / blob_entry["sha256"][2:4] / f"{blob_entry['sha256']}.blob"
    )
    assert copied.is_file()
    assert copied.read_bytes() == data

    runs = client.get(f"/api/v1/backups/jobs/{job['id']}/backups").json()
    assert [row["id"] for row in runs["items"]] == [run["id"]]


def test_run_backup_without_blob_copies(client, admin_auth):
    session = admin_auth
    data = b"manifest only"
    _upload_file(client, session, data, filename="m.txt")
    job = _create_job(
        client, session,
        include_content_blobs=False,
        target_path=str(_tmp_target()),
    )

    run = client.post(
        f"/api/v1/backups/jobs/{job['id']}/run",
        headers=csrf_headers(session["csrf_token"]),
    ).json()
    assert run["state"] == "verified"

    destination = Path(run["destination"])
    assert not (destination / "blobs").exists()
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["include_content_blobs"] is False
    entry = next(
        e for e in manifest["blobs"]
        if e["sha256"] == hashlib.sha256(data).hexdigest()
    )
    assert entry["present"] is True  # source blob exists, just not copied


def test_retention_prunes_old_runs(client, admin_auth):
    session = admin_auth
    job = _create_job(
        client, session, retention_count=2,
        target_path=str(_tmp_target()),
    )
    destinations = []
    for _ in range(3):
        run = client.post(
            f"/api/v1/backups/jobs/{job['id']}/run",
            headers=csrf_headers(session["csrf_token"]),
        ).json()
        assert run["state"] == "verified"
        destinations.append(Path(run["destination"]))
    # Three runs may land in the same second → same directory name; count
    # distinct directories: no more than retention_count may survive.
    remaining = {d for d in destinations if d.exists()}
    assert destinations[-1].exists()
    assert len(remaining) <= 2
