"""Admin console tests: overview, user controls, audit feed, RBAC."""

from __future__ import annotations

from tests.conftest import csrf_headers


def _create_user(client, email="member@example.com", password="member-pass-1") -> str:
    from app.core.database import get_sessionmaker
    from app.models import User, new_id, utcnow
    from app.security.password import hash_password

    with get_sessionmaker().begin() as db:
        user = User(
            id=new_id(),
            email=email,
            display_name="Member",
            password_hash=hash_password(password),
            role="user",
            is_admin=False,
            is_active=True,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(user)
        return user.id


def test_admin_overview_users_and_audit(client, admin_auth):
    session = admin_auth
    user_id = _create_user(client)

    overview = client.get("/api/v1/admin/overview").json()
    assert overview["users"] == 2
    assert overview["active_users"] == 2
    assert overview["admins"] == 1
    assert "files" in overview and "bytes" in overview

    users = client.get("/api/v1/admin/users").json()["items"]
    assert {row["id"] for row in users} == {
        client.get("/api/v1/auth/me").json()["id"], user_id
    }
    assert next(row for row in users if row["id"] == user_id)["is_admin"] is False

    patched = client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"is_admin": True},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_admin"] is True
    assert patched.json()["role"] == "admin"
    assert client.get("/api/v1/admin/overview").json()["admins"] == 2

    audit = client.get("/api/v1/admin/audit").json()["items"]
    assert any(row["action"] == "admin.user.updated" for row in audit)


def test_admin_cannot_demote_self(client, admin_auth):
    session = admin_auth
    my_id = client.get("/api/v1/auth/me").json()["id"]
    response = client.patch(
        f"/api/v1/admin/users/{my_id}",
        json={"is_admin": False},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert response.status_code == 409


def test_non_admin_is_blocked(client, admin_auth):
    _create_user(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": "member-pass-1"},
    )
    assert login.status_code == 200, login.text
    assert client.get("/api/v1/admin/overview").status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/admin/audit").status_code == 403


def test_admin_requires_auth_and_csrf(client):
    assert client.get("/api/v1/admin/overview").status_code == 401
    assert client.patch(
        "/api/v1/admin/users/x", json={"is_admin": True}
    ).status_code in (401, 403)
