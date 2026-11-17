"""Hosting app-manager tests: validation, staged config, static files, RBAC."""

from __future__ import annotations

from tests.conftest import csrf_headers


def _create_app(client, session, **overrides) -> dict:
    payload = {
        "name": "demo-site",
        "kind": "static",
        "domain": "demo.local",
        "path_prefix": "/",
        **overrides,
    }
    response = client.post(
        "/api/v1/hosting/apps", json=payload,
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_static_app_lifecycle_and_staged_config(client, admin_auth):
    session = admin_auth
    app = _create_app(client, session, description="My demo")
    assert app["kind"] == "static"
    assert app["root_path"]  # created under the user-owned data dir

    apps = client.get("/api/v1/hosting/apps").json()["items"]
    assert [row["id"] for row in apps] == [app["id"]]

    written = client.put(
        f"/api/v1/hosting/apps/{app['id']}/files",
        json={"path": "index.html", "content": "<h1>Hello</h1>"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert written.status_code == 200, written.text
    files = client.get(f"/api/v1/hosting/apps/{app['id']}/files").json()["items"]
    assert [row["path"] for row in files] == ["index.html"]

    staged = client.post(
        "/api/v1/hosting/config/stage",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert staged.status_code == 200, staged.text
    config = staged.json()["config"]
    assert "server_name demo.local;" in config
    assert "root " in config
    assert staged.json()["apply_script"].endswith("apply.sh")
    assert "/etc/nginx" in open(staged.json()["apply_script"]).read()

    disabled = client.patch(
        f"/api/v1/hosting/apps/{app['id']}",
        json={"enabled": False},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert disabled.json()["enabled"] is False
    assert "demo.local" not in client.get("/api/v1/hosting/config/preview").json()["config"]

    deleted = client.delete(
        f"/api/v1/hosting/apps/{app['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert deleted.status_code == 200
    assert client.get("/api/v1/hosting/apps").json()["items"] == []


def test_proxy_app_validation(client, admin_auth):
    session = admin_auth
    proxy = _create_app(
        client, session,
        name="api-app", domain="api.local", kind="proxy", upstream_port=9101,
    )
    assert proxy["upstream_port"] == 9101
    assert "proxy_pass http://127.0.0.1:9101;" in (
        client.get("/api/v1/hosting/config/preview").json()["config"]
    )

    duplicate_port = client.post(
        "/api/v1/hosting/apps",
        json={"name": "other", "kind": "proxy", "domain": "other.local",
              "upstream_port": 9101},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert duplicate_port.status_code == 409

    bad_name = client.post(
        "/api/v1/hosting/apps",
        json={"name": "../escape", "kind": "static", "domain": "x.local"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert bad_name.status_code == 400

    bad_path = client.put(
        f"/api/v1/hosting/apps/{proxy['id']}/files",
        json={"path": "../../etc/passwd", "content": "x"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert bad_path.status_code in (400, 409)


def test_hosting_requires_admin_and_csrf(client):
    assert client.get("/api/v1/hosting/apps").status_code == 401
    assert client.post("/api/v1/hosting/apps", json={"name": "x"}).status_code in (401, 403)
