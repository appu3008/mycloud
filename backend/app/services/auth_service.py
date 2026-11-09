"""Auth service: login, sessions, logout, password change.

Design notes
------------
- Sessions are DB rows keyed by sha256(session_token); the browser only sees
  the random token in an HttpOnly cookie.
- Two expiries: idle (last_seen) and absolute (created). Both enforced on
  every validation so stolen cookies age out even with activity.
- Lockout decisions come from audit rows (security/audit.py), shared by all
  workers and durable across restarts.
- Login failure responses are uniform ("invalid or locked") to prevent
  account enumeration.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session as SAMSession

from ..core.config import Settings
from ..models import Session, User, utcnow
from ..security import audit
from ..security.password import hash_password, needs_rehash, verify_password
from ..security.tokens import new_session_token

UNIFORM_LOGIN_ERROR = "invalid or locked"


def hash_cookie_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def create_session(
    db: SAMSession,
    settings: Settings,
    *,
    user: User,
    ip: str | None = None,
    user_agent: str | None = None,
    device_id: str | None = None,
) -> tuple[Session, str]:
    """Create and return (session_row, raw_cookie_token). Hash at rest only."""
    token = new_session_token()
    now = utcnow()
    row = Session(
        id=hash_cookie_token(token),
        user_id=user.id,
        device_id=device_id,
        ip_address=(ip or "")[:64] or None,
        user_agent=(user_agent or "")[:256] or None,
        csrf_token=secrets.token_urlsafe(32),
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        abs_expires_at=now + timedelta(hours=settings.session_absolute_ttl_hours),
    )
    db.add(row)
    return row, token


def validate_session(
    db: SAMSession, *, cookie_token: str | None
) -> tuple[User | None, Session | None]:
    """Resolve a cookie to (user, session) or (None, None).

    Enforces: hash exists, not revoked, both expiries, user is active.
    """
    if not cookie_token:
        return None, None
    row = db.get(Session, hash_cookie_token(cookie_token))
    if row is None or row.revoked_at is not None:
        return None, None
    now = utcnow()
    if row.expires_at < now or row.abs_expires_at < now:
        return None, None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None, None
    return user, row


def touch(session: Session, settings: Settings) -> None:
    """Sliding idle window; never extends beyond the absolute expiry."""
    now = utcnow()
    session.last_seen_at = now
    idle_expiry = now + timedelta(hours=settings.session_ttl_hours)
    session.expires_at = min(session.abs_expires_at, idle_expiry)


def revoke(db: SAMSession, session_id: str) -> int:
    result = db.execute(
        update(Session)
        .where(Session.id == session_id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    return int(result.rowcount or 0)


def revoke_all_for_user(db: SAMSession, user_id: str, *, except_session_id: str | None) -> int:
    stmt = update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    if except_session_id:
        stmt = stmt.where(Session.id != except_session_id)
    result = db.execute(stmt.values(revoked_at=utcnow()))
    return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def authenticate(
    db: SAMSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip: str | None,
) -> tuple[User | None, Session | None, str | None, int | None]:
    """Return (user, session, cookie_token, retry_after_seconds).

    On success cookie_token+session are returned; on failure token is None
    and retry_after is non-None when the identity is currently locked out.
    """
    email_key = email.strip().lower()

    locked, retry_after = audit.lockout_status(
        db, email=email_key, ip=ip, settings=settings
    )
    if locked:
        audit.record_locked_attempt(db, email=email_key, ip=ip)
        db.commit()  # security rows survive 401 teardown
        return None, None, None, retry_after

    user = db.execute(select(User).where(User.email == email_key)).scalar_one_or_none()
    if user is None or not user.is_active:
        audit.record_audit(
            db,
            action=audit.FAILED_LOGIN_ACTION,
            actor_email=email_key,
            actor_ip=ip,
            detail={"reason": "unknown_or_disabled"},
        )
        db.commit()  # security rows survive 401 teardown
        return None, None, None, None

    if not verify_password(password, user.password_hash):
        audit.record_audit(
            db,
            action=audit.FAILED_LOGIN_ACTION,
            actor_email=email_key,
            actor_ip=ip,
            detail={"reason": "bad_password"},
        )
        db.commit()  # security rows survive 401 teardown
        return None, None, None, None

    # Transparent rehash when Argon2id parameters were upgraded since login.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = utcnow()
    session_row, token = create_session(
        db, settings, user=user, ip=ip
    )
    return user, session_row, token, None


def csrf_matches(session: Session, header_value: str | None) -> bool:
    """Constant-time comparison of header CSRF against the session token."""
    if not header_value:
        return False
    from ..security.tokens import constant_time_equals

    return constant_time_equals(session.csrf_token, header_value)
