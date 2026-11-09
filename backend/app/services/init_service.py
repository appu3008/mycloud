"""First-admin enrollment (spec section 13 — no default credentials).

The init flow is open ONLY while the system has zero admins. Creating the
first admin permanently closes it (403 thereafter). A marker file (mode 0600)
in the database directory records that enrollment happened, so the closure
survives even a corrupted users table.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import Settings
from ..models import User, new_id
from ..security import audit
from ..security.password import hash_password


def marker_path(settings: Settings) -> Path:
    return settings.data_dir / settings.admin_marker_file


def marker_exists(settings: Settings) -> bool:
    return marker_path(settings).exists()


def close_enrollment(settings: Settings) -> None:
    """Write the 0600 marker. Idempotent; content is not a secret."""
    path = marker_path(settings)
    path.touch(exist_ok=True)
    path.chmod(0o600)


def admin_count(db: SAMSession) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        ).scalar_one()
    )


def enrollment_open(db: SAMSession, settings: Settings) -> bool:
    return admin_count(db) == 0 and not marker_exists(settings)


def create_first_admin(
    db: SAMSession,
    settings: Settings,
    *,
    email: str,
    display_name: str,
    password: str,
    ip: str | None,
) -> User | None:
    """Create the administrator iff enrollment is open; None otherwise."""
    if not enrollment_open(db, settings):
        return None
    user = User(
        id=new_id(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
        display_name=display_name.strip()[:128] or display_name,
        role="admin",
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    close_enrollment(settings)
    audit.record_audit(
        db,
        action="auth.admin.enrolled",
        actor_email=user.email,
        actor_ip=ip,
        detail={"via": "provider_init"},
    )
    db.flush()  # ensure users row exists before later FK references same txn
    return user
