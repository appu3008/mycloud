"""Activity timeline service: lightweight per-user event feed."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..models import ActivityEvent, utcnow

_MAX_SUMMARY = 500


def log_event(
    db: SAMSession,
    *,
    user_id: str,
    kind: str,
    summary: str,
    file_id: str | None = None,
) -> None:
    """Append an event; failures never break the caller's operation."""
    try:
        db.add(
            ActivityEvent(
                user_id=user_id,
                kind=kind,
                file_id=file_id,
                summary=summary[:_MAX_SUMMARY],
                created_at=utcnow(),
            )
        )
    except Exception:  # pragma: no cover - activity must never break a request
        pass


def list_events(
    db: SAMSession, *, user_id: str, limit: int = 50, offset: int = 0
) -> dict:
    limit = max(1, min(limit, 200))
    rows = db.execute(
        select(ActivityEvent)
        .where(ActivityEvent.user_id == user_id)
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    total = int(
        db.execute(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.user_id == user_id
            )
        ).scalar_one()
    )
    return {
        "items": [
            {
                "id": row.id,
                "kind": row.kind,
                "file_id": row.file_id,
                "summary": row.summary,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "total": total,
    }
