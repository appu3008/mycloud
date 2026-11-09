"""Auth phase tests: enrollment, login, CSRF, lockout, revocation, history."""

from __future__ import annotations

from tests.conftest import csrf_headers


def test_health_reports_real_database(client):
    response = client.get("/api/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["database"]["reachable"] is True
    assert body["database"]["foreign_keys"] is True
    assert body["database"]["journal_mode"] == "wal"


def test_first_admin_enrollment_open_then_closed(client, app_env):
    status = client.get("/api/v1/auth/provider/init/status").json()
    assert status["enrollment_open"] is True

    enroll = client.post(
        "/api/v1/auth/provider/init",
        json={"email": "root@example.com", "display_name": "Root", "password": "correct-horse-9"},
    )
    assert enroll.status_code == 201, enroll.text
    assert enroll.json()["user"]["is_admin"] is True
    assert "mycloud_session" in client.cookies

    # Second enrollment must be permanently refused.
    again = client.post(
        "/api/v1/auth/provider/init",
        json={"email": "other@example.com", "display_name": "X", "password": "another-pass-99"},
    )
    assert again.status_code == 403
    assert client.get("/api/v1/auth/provider/init/status").json()["enrollment_open"] is False
    # Marker survived as a file (mode 0600 semantics checked here).
    from app.core.config import get_settings
    from app.services import init_service

    marker = init_service.marker_path(get_settings())
    assert marker.exists()
    assert (marker.stat().st_mode & 0o077) == 0


def test_login_success_failure_and_uniform_errors(client, admin_auth):
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "x"}
    )
    bad_pass = client.post(
        "/api/v1/auth/login", json={"email": admin_auth["email"], "password": "wrong-pass-1"}
    )
    assert wrong.status_code == 401 and bad_pass.status_code == 401
    assert (
        wrong.json()["detail"]["error"]
        == bad_pass.json()["detail"]["error"]
        == "invalid or locked"
    )

    good = client.post(
        "/api/v1/auth/login",
        json={"email": admin_auth["email"], "password": admin_auth["password"]},
    )
    assert good.status_code == 200
    assert good.json()["csrf_token"]
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == admin_auth["email"]


def test_csrf_required_on_mutations(client, admin_auth):
    # Without the header -> 403.
    no_header = client.patch(
        "/api/v1/auth/me", json={"display_name": "Renamed"}
    )
    assert no_header.status_code == 403
    assert no_header.json()["detail"]["error"].startswith("csrf")

    # With the header -> 200 and persisted.
    ok = client.patch(
        "/api/v1/auth/me",
        json={"display_name": "Renamed"},
        headers=csrf_headers(admin_auth["csrf_token"]),
    )
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").json()["display_name"] == "Renamed"


def test_brute_force_lockout_is_durable(client, admin_auth):
    email = admin_auth["email"]
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": email, "password": "bad-pass-1"})
    valid_but_locked = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": admin_auth["password"]},
    )
    assert valid_but_locked.status_code == 401
    body = valid_but_locked.json()["detail"]
    assert body["error"] == "invalid or locked"
    assert body.get("retry_after_seconds", 0) > 0


def test_logout_revokes_and_cookie_clears(client, admin_auth):
    assert client.get("/api/v1/auth/me").status_code == 200
    out = client.post(
        "/api/v1/auth/logout", headers=csrf_headers(admin_auth["csrf_token"])
    )
    assert out.status_code == 200
    me_after = client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


def test_password_change_revokes_other_sessions(client, admin_auth):
    from fastapi.testclient import TestClient

    second = TestClient(client.app)
    second.post(
        "/api/v1/auth/login",
        json={"email": admin_auth["email"], "password": admin_auth["password"]},
    )
    assert second.get("/api/v1/auth/me").status_code == 200

    change = client.patch(
        "/api/v1/auth/me/password",
        json={"current_password": admin_auth["password"], "new_password": "new-pass-2026x"},
        headers=csrf_headers(admin_auth["csrf_token"]),
    )
    assert change.status_code == 200, change.text
    assert change.json()["sessions_revoked"] >= 1

    assert second.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 200  # current session lives

    # Old password no longer works; new one does.
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin_auth["email"], "password": admin_auth["password"]},
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin_auth["email"], "password": "new-pass-2026x"},
    )
    assert new_login.status_code == 200


def test_revoke_other_session_by_id(client, admin_auth):
    from fastapi.testclient import TestClient

    victim = TestClient(client.app)
    victim.post(
        "/api/v1/auth/login",
        json={"email": admin_auth["email"], "password": admin_auth["password"]},
    )
    sessions = client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2
    target = next(s["id"] for s in sessions if not s["is_current"])

    response = client.delete(
        f"/api/v1/auth/sessions/{target}",
        headers=csrf_headers(admin_auth["csrf_token"]),
    )
    assert response.status_code == 200
    assert victim.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 200


def test_login_history_records_attempts(client, admin_auth):
    client.post("/api/v1/auth/login", json={"email": admin_auth["email"], "password": "bad-1"})
    client.post(
        "/api/v1/auth/login", json={"email": admin_auth["email"], "password": admin_auth["password"]}
    )
    history = client.get("/api/v1/auth/login-history").json()
    actions = [entry["action"] for entry in history]
    assert "auth.login.failed" in actions
    assert "auth.login.success" in actions
    assert all("password" not in entry and "token" not in entry for entry in history)


def test_registration_disabled_until_invites(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "display_name": "New", "password": "some-pass-999"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "registration_disabled"
