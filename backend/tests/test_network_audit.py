"""Authorized network-audit tests: scope enforcement, local-only scans."""

from __future__ import annotations

import socket

from tests.conftest import csrf_headers


def _scope(client, session, cidr="127.0.0.0/8", **fields) -> dict:
    payload = {"name": "Local lab", "cidr": cidr, "notes": "owned by me", **fields}
    response = client.post(
        "/api/v1/security/scopes", json=payload,
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_scope_validation_and_listing(client, admin_auth):
    session = admin_auth
    scope = _scope(client, session)
    assert scope["cidr"] == "127.0.0.0/8"
    assert scope["enabled"] is True
    assert [row["id"] for row in client.get("/api/v1/security/scopes").json()["items"]] == [scope["id"]]

    public = client.post(
        "/api/v1/security/scopes",
        json={"name": "Internet", "cidr": "8.8.8.0/24"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert public.status_code == 400
    assert public.json()["detail"]["error"] == "scope_must_be_private"

    duplicate = client.post(
        "/api/v1/security/scopes",
        json={"name": "Again", "cidr": "127.0.0.0/8"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert duplicate.status_code == 409

    disabled = client.post(
        f"/api/v1/security/scopes/{scope['id']}/disable",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert disabled.status_code == 200
    assert client.get("/api/v1/security/scopes").json()["items"][0]["enabled"] is False


def test_scan_rejects_public_and_out_of_scope_targets(client, admin_auth):
    session = admin_auth
    scope = _scope(client, session)

    public = client.post(
        "/api/v1/security/scans",
        json={"scope_id": scope["id"], "target": "8.8.8.8", "ports": [80]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert public.status_code == 400
    assert public.json()["detail"]["error"] == "public_target_rejected"

    outside = client.post(
        "/api/v1/security/scans",
        json={"scope_id": scope["id"], "target": "192.168.5.4", "ports": [80]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert outside.status_code == 403
    assert outside.json()["detail"]["error"] == "target_outside_scope"


def test_scan_finds_local_listener_and_records_report(client, admin_auth):
    session = admin_auth
    scope = _scope(client, session)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port = listener.getsockname()[1]
    try:
        scan = client.post(
            "/api/v1/security/scans",
            json={"scope_id": scope["id"], "target": "127.0.0.1", "ports": [port, 9]},
            headers=csrf_headers(session["csrf_token"]),
        )
        assert scan.status_code == 201, scan.text
        result = scan.json()
        assert result["scan"]["state"] == "completed"
        assert result["scan"]["findings_count"] == 1
        assert result["findings"][0]["port"] == port
    finally:
        listener.close()

    report = client.get(f"/api/v1/security/scans/{result['scan']['id']}").json()
    assert report["findings"][0]["severity"] in {"low", "medium", "high"}
    assert any(row["id"] == result["scan"]["id"] for row in client.get("/api/v1/security/scans").json()["items"])


def test_hardening(client, admin_auth):
    checks = client.get("/api/v1/security/hardening").json()["items"]
    assert {row["id"] for row in checks} >= {"production_env", "secret_key", "cors", "backups"}


def test_security_requires_auth(client):
    assert client.get("/api/v1/security/scopes").status_code == 401
    assert client.post("/api/v1/security/scans", json={}).status_code in (401, 403)
