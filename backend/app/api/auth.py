"""Auth API (v1): first-admin init, login, logout, profile, sessions.

Mutating routes use csrf_protected_auth (X-CSRF-Token + origin check).
Logout intentionally accepts a missing CSRF header: an attacker gains
nothing by force-logging a victim out, and this avoids locking out users
with stale CSRF tokens. Registering is closed (Phase 12 invites).
"""

from __future__ import annotations

import secrets  # noqa: F401 — used by future challenge flows via public helpers
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import get_settings
from ..core.database import get_db
from ..models import AuditLog, User, utcnow
from ..models import Session as SessionRow
from ..schemas.auth import (
    InitStatus,
    LoginRequest,
    LoginSuccess,
    PasswordChange,
    ProfileUpdate,
    ProviderInitRequest,
    RegisterRequest,
    SessionInfo,
    UserInfo,
)
from ..security import audit
from ..security.password import hash_password, verify_password
from ..services import activity_service, auth_service, init_service
from .dependencies import csrf_protected_auth, get_current_auth, get_request_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )


@router.get("/provider/init/status", response_model=InitStatus)
def init_status(db: SAMSession = Depends(get_db)) -> InitStatus:
    if init_service.enrollment_open(db, get_settings()):
        return InitStatus(enrollment_open=True, reason="no admin exists")
    if init_service.admin_count(db) > 0:
        return InitStatus(enrollment_open=False, reason="admin already exists")
    return InitStatus(enrollment_open=False, reason="enrollment already used")


@router.post(
    "/provider/init", response_model=LoginSuccess, status_code=status.HTTP_201_CREATED
)
def provider_init(
    body: ProviderInitRequest,
    request: Request,
    response: Response,
    db: SAMSession = Depends(get_db),
) -> LoginSuccess:
    """One-time creation of the first administrator (no default creds)."""
    settings = get_settings()
    ip = get_request_ip(request)
    user = init_service.create_first_admin(
        db,
        settings,
        email=str(body.email),
        display_name=body.display_name,
        password=body.password,
        ip=ip,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "enrollment_closed"},
        )
    session_row, token = auth_service.create_session(db, settings, user=user, ip=ip)
    db.commit()
    _set_session_cookie(response, token)
    return LoginSuccess(csrf_token=session_row.csrf_token, user=UserInfo.model_validate(user))


@router.post("/login", response_model=LoginSuccess)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: SAMSession = Depends(get_db),
) -> LoginSuccess:
    settings = get_settings()
    ip = get_request_ip(request)
    user, session_row, token, retry_after = auth_service.authenticate(
        db, settings, email=str(body.email), password=body.password, ip=ip
    )
    if user is None or token is None or session_row is None:
        detail: dict = {"error": auth_service.UNIFORM_LOGIN_ERROR}
        if retry_after:
            detail["retry_after_seconds"] = retry_after
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    db.commit()
    _set_session_cookie(response, token)
    audit.record_audit(
        db,
        action="auth.login.success",
        actor_user_id=user.id,
        actor_email=user.email,
        actor_ip=ip,
    )
    activity_service.log_event(
        db, user_id=user.id, kind="login", summary=f"Signed in from {ip}"
    )
    db.commit()
    return LoginSuccess(csrf_token=session_row.csrf_token, user=UserInfo.model_validate(user))


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: SAMSession = Depends(get_db),
) -> dict:
    cookie_token = request.cookies.get(get_settings().session_cookie_name)
    user, session_row = auth_service.validate_session(db, cookie_token=cookie_token)
    if user is not None and session_row is not None:
        auth_service.revoke(db, session_row.id)
        db.commit()
        audit.record_audit(
            db,
            action="auth.logout",
            actor_user_id=user.id,
            actor_ip=get_request_ip(request),
        )
        activity_service.log_event(db, user_id=user.id, kind="logout", summary="Signed out")
        db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserInfo)
def me(auth: tuple[User, SessionRow] = Depends(get_current_auth)) -> UserInfo:
    user, _ = auth
    return UserInfo.model_validate(user)


@router.patch("/me", response_model=UserInfo)
def update_profile(
    body: ProfileUpdate,
    request: Request,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> UserInfo:
    user, _ = auth
    user.display_name = body.display_name
    db.commit()
    audit.record_audit(
        db,
        action="auth.profile.updated",
        actor_user_id=user.id,
        actor_ip=get_request_ip(request),
    )
    db.commit()
    return UserInfo.model_validate(user)


@router.patch("/me/password")
def change_password(
    body: PasswordChange,
    request: Request,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, session = auth
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "current_password_invalid"}
        )
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    revoked_others = auth_service.revoke_all_for_user(
        db, user.id, except_session_id=session.id
    )
    db.commit()
    audit.record_audit(
        db,
        action="auth.password.changed",
        actor_user_id=user.id,
        actor_ip=get_request_ip(request),
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    return {"ok": True, "sessions_revoked": revoked_others}


@router.get("/sessions", response_model=list[SessionInfo])
def list_sessions(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> list[SessionInfo]:
    user, current = auth
    rows = (
        db.execute(
            select(SessionRow)
            .where(SessionRow.user_id == user.id, SessionRow.revoked_at.is_(None))
            .order_by(SessionRow.last_seen_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        SessionInfo(
            id=row.id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            device_id=row.device_id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            is_current=row.id == current.id,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    request: Request,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, current = auth
    if session_id != current.id:
        row = db.get(SessionRow, session_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail={"error": "session_not_found"}
            )
    auth_service.revoke(db, session_id)
    db.commit()
    audit.record_audit(
        db,
        action="auth.session.revoked",
        actor_user_id=user.id,
        actor_ip=get_request_ip(request),
        target_type="session",
        target_id=session_id,
    )
    db.commit()
    return {"ok": True}


@router.get("/login-history")
def login_history(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> list[dict]:
    """Own login history (success/failed attempts), newest first, capped 200.

    Values shown: action, ip, timestamp — never secrets or token material.
    """
    user, _ = auth
    since = utcnow() - timedelta(days=90)
    rows = (
        db.execute(
            select(AuditLog)
            .where(
                AuditLog.action.in_(("auth.login.success", "auth.login.failed")),
                AuditLog.actor_email == user.email,
                AuditLog.created_at > since,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )
    return [
        {
            "action": row.action,
            "ip": row.actor_ip,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/register")
def register(body: RegisterRequest, db: SAMSession = Depends(get_db)) -> None:
    """Closed until Phase 12 invites exist. Real, honest behavior:
    reporting disabled rather than pretending registration works."""
    settings = get_settings()
    if not settings.allow_registration:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail={"error": "registration_disabled"}
        )
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail={"error": "registration_requires_invite", "phase": 12},
    )
