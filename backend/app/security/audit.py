"""Login auditing + brute-force lockout (durable, multi-worker safe).

Login failure counting rides on audit_logs rows, so the policy survives
process restarts and is shared across uvicorn workers — no in-memory state.
Per-account and per-IP failure caps are enforced with distinct windows.
Nothing resembling passwords, tokens, or secrets is ever recorded here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import Settings
from ..models import AuditLog, utcnow

FAILED_LOGIN_ACTION = "auth.login.failed"
LOCKED_LOGIN_ACTION = "auth.login.locked"

# Extra guard against password spraying from one IP (distinct from account cap).
IP_FAILED_EXTRA_FACTOR = 4


def record_audit(
    db: SAMSession,
    *,
    action: str,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    actor_ip: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append one audit row (SECURITY.md: detail never contains secrets)."""
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_email=(actor_email or "")[:255] or None,
            actor_ip=(actor_ip or "")[:64] or None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=json.dumps(detail or {}, separators=(",", ":")),
            created_at=utcnow(),
        )
    )


def lockout_status(
    db: SAMSession, *, email: str | None, ip: str | None, settings: Settings
) -> tuple[bool, int]:
    """(locked, unauthenticated-path retry after seconds).

    Locked when either the account or the source IP hit their failure cap
    within the attempt window; retry_after uses the most recent failure.
    """
    if not email:
        return False, 0

    account_rows = db.execute(
        select(AuditLog.created_at)
        .where(
            AuditLog.action == FAILED_LOGIN_ACTION,
            AuditLog.actor_email == email,
            AuditLog.created_at
            > utcnow() - timedelta(minutes=settings.login_attempt_window_minutes),
        )
        .order_by(AuditLog.created_at.desc())
    ).all()
    account_failures = len(account_rows)

    if ip:
        ip_failures = len(
            db.execute(
                select(AuditLog.id).where(
                    AuditLog.action == FAILED_LOGIN_ACTION,
                    AuditLog.actor_ip == ip,
                    AuditLog.created_at
                    > utcnow() - timedelta(minutes=settings.login_attempt_window_minutes),
                )
            ).all()
        )
    else:
        ip_failures = 0

    threshold = settings.login_max_failed_attempts
    if account_failures >= threshold or ip_failures >= threshold * IP_FAILED_EXTRA_FACTOR:
        last: datetime | None = account_rows[0][0] if account_rows else None
        retry_after = 0
        if last is not None:
            elapsed_min = (utcnow() - last).total_seconds() / 60.0
            retry_after = max(0, int((settings.login_lockout_minutes - elapsed_min) * 60))
        return True, retry_after

    return False, 0


def record_locked_attempt(db: SAMSession, *, email: str | None, ip: str | None) -> None:
    record_audit(db, action=LOCKED_LOGIN_ACTION, actor_email=email, actor_ip=ip)
