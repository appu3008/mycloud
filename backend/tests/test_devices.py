"""Device + sync tests: trust gates, heartbeat, backup config, conflicts."""

from __future__ import annotations

import hashlib

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for


def _upload(client, session, data: bytes) -> dict:
    init = client.post(
        "/api/v1/uploads",
        json={"filename": "sync.txt", "size_bytes": len(data),
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


def _register(client, session, name="Pixel", platform="android") -> dict:
    response = client.post(
        "/api/v1/devices",
        json={"name": name, "platform": platform, "public_key": "ed25519:abc"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _trust(client, session, device_id: str, **fields) -> dict:
    response = client.patch(
        f"/api/v1/devices/{device_id}",
        json={"trust_level": "trusted", **fields},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_registration_is_untrusted_and_gates_sync(client, admin_auth):
    session = admin_auth
    device = _register(client, session)
    assert device["trust_level"] == "untrusted"
    assert device["can_sync"] is False and device["can_backup"] is False
    assert device["has_public_key"] is True
    assert device["platform"] == "android"

    file_row = _upload(client, session, b"sync payload")
    blocked = client.post(
        "/api/v1/sync/jobs",
        json={"device_id": device["id"], "file_id": file_row["id"], "direction": "down"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert blocked.status_code == 403

    assert client.get(f"/api/v1/devices/{device['id']}/backup-config").status_code == 403


def test_trust_heartbeat_and_android_backup_config(client, admin_auth):
    session = admin_auth
    device = _register(client, session)
    trusted = _trust(client, session, device["id"], can_sync=True, can_backup=True)
    assert trusted["trust_level"] == "trusted"
    assert trusted["can_sync"] and trusted["can_backup"]

    beat = client.post(
        f"/api/v1/devices/{device['id']}/heartbeat",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert beat.status_code == 200
    assert beat.json()["last_seen_at"]

    config = client.get(f"/api/v1/devices/{device['id']}/backup-config").json()
    assert config["upload_endpoint"] == "/api/v1/uploads"
    assert config["chunk_checksum_header"] == "X-Chunk-Sha256"
    assert config["auth"] == "session cookie + X-CSRF-Token header"
    assert config["max_chunk_mb"] == 16


def test_sync_conflict_and_resolution(client, admin_auth):
    session = admin_auth
    device = _trust(client, session, _register(client, session)["id"], can_sync=True)
    file_row = _upload(client, session, b"server bytes")
    server_sha = hashlib.sha256(b"server bytes").hexdigest()

    conflicting = client.post(
        "/api/v1/sync/jobs",
        json={
            "device_id": device["id"], "file_id": file_row["id"],
            "direction": "down", "local_checksum": "f" * 64,
        },
        headers=csrf_headers(session["csrf_token"]),
    )
    assert conflicting.status_code == 201, conflicting.text
    job = conflicting.json()
    assert job["state"] == "conflict"
    assert job["server_checksum"] == server_sha

    resolved = client.post(
        f"/api/v1/sync/jobs/{job['id']}/resolve",
        json={"strategy": "accept_server"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "done"
    assert resolved.json()["conflict_strategy"] == "accept_server"

    # A matching checksum completes without a conflict.
    clean = client.post(
        "/api/v1/sync/jobs",
        json={
            "device_id": device["id"], "file_id": file_row["id"],
            "direction": "down", "local_checksum": server_sha,
        },
        headers=csrf_headers(session["csrf_token"]),
    ).json()
    assert clean["state"] == "queued"
    done = client.post(
        f"/api/v1/sync/jobs/{clean['id']}/complete",
        json={"checksum": server_sha},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert done.json()["state"] == "done"

    jobs = client.get(f"/api/v1/sync/jobs?device_id={device['id']}").json()["items"]
    assert len(jobs) == 2


def test_revoke_device_blocks_future_sync(client, admin_auth):
    session = admin_auth
    device = _trust(client, session, _register(client, session)["id"], can_sync=True)
    revoked = client.patch(
        f"/api/v1/devices/{device['id']}",
        json={"revoke": True},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert revoked.json()["can_sync"] is False
    assert client.post(
        f"/api/v1/devices/{device['id']}/heartbeat",
        headers=csrf_headers(session["csrf_token"]),
    ).status_code == 410


def test_devices_require_auth(client):
    assert client.get("/api/v1/devices").status_code == 401
    assert client.get("/api/v1/sync/jobs").status_code == 401
