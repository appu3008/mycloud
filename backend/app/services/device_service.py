"""Device registration, trust and sync-job orchestration.

A newly registered device is untrusted: it can appear in the UI but cannot
queue or run sync jobs until an authenticated user grants trust. Revoked
devices are kept as a record (with their jobs) rather than erased.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..models import ActivityEvent, Device, SyncJob, new_id, utcnow

VALID_PLATFORMS = {"android", "ios", "linux", "macos", "windows", "web", "generic"}
VALID_STRATEGIES = {"accept_local", "accept_server", "newer_wins", "conflict_copy"}


def register_device(
    db: SAMSession,
    *,
    user_id: str,
    name: str,
    platform: str,
    public_key: str | None = None,
) -> Device:
    clean_name = name.strip()[:128]
    if not clean_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_name"})
    if platform not in VALID_PLATFORMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_platform"})
    device = Device(
        id=new_id(),
        user_id=user_id,
        name=clean_name,
        platform=platform,
        public_key=public_key or None,
        trust_level="untrusted",
        can_sync=False,
        can_backup=False,
        last_seen_at=utcnow(),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(device)
    _activity(db, user_id=user_id, kind="device", summary=f"Registered device \u201c{clean_name}\u201d")
    return device


def _activity(db: SAMSession, *, user_id: str, kind: str, summary: str) -> None:
    db.add(
        ActivityEvent(
            id=new_id(), user_id=user_id, kind=kind, summary=summary[:500], created_at=utcnow()
        )
    )


def owned_device(db: SAMSession, *, user_id: str, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "device_not_found"})
    return device


def device_dict(db: SAMSession, device: Device) -> dict:
    jobs = db.execute(
        select(SyncJob.state, SyncJob.id).where(SyncJob.device_id == device.id)
    ).all()
    return {
        "id": device.id,
        "name": device.name,
        "platform": device.platform,
        "has_public_key": bool(device.public_key),
        "trust_level": device.trust_level,
        "can_sync": device.can_sync,
        "can_backup": device.can_backup,
        "last_seen_at": device.last_seen_at,
        "revoked_at": device.revoked_at,
        "job_count": len(jobs),
        "conflict_count": sum(1 for state, _ in jobs if state == "conflict"),
    }


def list_devices(db: SAMSession, *, user_id: str) -> list[dict]:
    rows = db.execute(
        select(Device)
        .where(Device.user_id == user_id)
        .order_by(Device.created_at.desc())
    ).scalars().all()
    return [device_dict(db, row) for row in rows]


def update_device(
    db: SAMSession,
    *,
    user_id: str,
    device_id: str,
    trust_level: str | None,
    can_sync: bool | None,
    can_backup: bool | None,
    revoke: bool,
) -> Device:
    device = owned_device(db, user_id=user_id, device_id=device_id)
    if trust_level is not None:
        if trust_level not in {"untrusted", "trusted"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_trust_level"})
        device.trust_level = trust_level
        if trust_level == "untrusted":
            device.can_sync = False
            device.can_backup = False
    if can_sync is not None:
        if can_sync and device.trust_level != "trusted":
            raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "device_not_trusted"})
        device.can_sync = can_sync
    if can_backup is not None:
        if can_backup and device.trust_level != "trusted":
            raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "device_not_trusted"})
        device.can_backup = can_backup
    if revoke:
        device.revoked_at = device.revoked_at or utcnow()
        device.can_sync = False
        device.can_backup = False
    _activity(
        db, user_id=user_id, kind="device",
        summary=f"Updated device \u201c{device.name}\u201d"
        + (" (revoked)" if revoke else ""),
    )
    return device


def heartbeat(db: SAMSession, *, user_id: str, device_id: str) -> Device:
    device = owned_device(db, user_id=user_id, device_id=device_id)
    if device.revoked_at is not None:
        raise HTTPException(status.HTTP_410_GONE, detail={"error": "device_revoked"})
    device.last_seen_at = utcnow()
    return device


def backup_config(db: SAMSession, *, user_id: str, device_id: str) -> dict:
    """What an Android backup client needs to start streaming uploads."""
    device = owned_device(db, user_id=user_id, device_id=device_id)
    if device.revoked_at is not None:
        raise HTTPException(status.HTTP_410_GONE, detail={"error": "device_revoked"})
    if not device.can_backup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "backup_not_allowed"})
    return {
        "device_id": device.id,
        "device_name": device.name,
        "upload_endpoint": "/api/v1/uploads",
        "chunk_endpoint": "/api/v1/uploads/{upload_id}/chunks/{number}",
        "complete_endpoint": "/api/v1/uploads/{upload_id}/complete",
        "auth": "session cookie + X-CSRF-Token header",
        "chunk_checksum_header": "X-Chunk-Sha256",
        "max_chunk_mb": 16,
        "trust_level": device.trust_level,
    }


# --- sync jobs -------------------------------------------------------------------

def queue_sync(
    db: SAMSession,
    *,
    user_id: str,
    device_id: str,
    file_id: str,
    direction: str,
    local_checksum: str | None,
    conflict_strategy: str | None,
) -> SyncJob:
    from .file_service import get_file_owned

    device = owned_device(db, user_id=user_id, device_id=device_id)
    if device.revoked_at is not None or not device.can_sync:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "device_cannot_sync"})
    if direction not in {"up", "down"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_direction"})
    if conflict_strategy is not None and conflict_strategy not in VALID_STRATEGIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_strategy"})
    file_row = get_file_owned(db, user_id=user_id, file_id=file_id)

    server_sha = file_row.blob_sha256
    state = "queued"
    if local_checksum and direction == "down" and local_checksum != server_sha:
        state = "conflict"
    job = SyncJob(
        id=new_id(),
        device_id=device.id,
        file_id=file_row.id,
        direction=direction,
        state=state,
        local_checksum=local_checksum,
        server_checksum=server_sha,
        conflict_strategy=conflict_strategy,
        attempts=0,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(job)
    return job


def job_dict(job: SyncJob) -> dict:
    return {
        "id": job.id,
        "device_id": job.device_id,
        "file_id": job.file_id,
        "direction": job.direction,
        "state": job.state,
        "local_checksum": job.local_checksum,
        "server_checksum": job.server_checksum,
        "conflict_strategy": job.conflict_strategy,
        "attempts": job.attempts,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def owned_job(db: SAMSession, *, user_id: str, job_id: str) -> SyncJob:
    job = db.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "job_not_found"})
    owned_device(db, user_id=user_id, device_id=job.device_id)
    return job


def list_jobs(db: SAMSession, *, user_id: str, device_id: str | None) -> list[dict]:
    stmt = select(SyncJob).order_by(SyncJob.created_at.desc())
    if device_id:
        owned_device(db, user_id=user_id, device_id=device_id)
        stmt = stmt.where(SyncJob.device_id == device_id)
    else:
        stmt = stmt.join(Device, SyncJob.device_id == Device.id).where(
            Device.user_id == user_id
        )
    return [job_dict(row) for row in db.execute(stmt).scalars().all()]


def complete_job(db: SAMSession, *, user_id: str, job_id: str, checksum: str | None) -> SyncJob:
    job = owned_job(db, user_id=user_id, job_id=job_id)
    if job.state in ("done", "conflict"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "job_finished"})
    job.attempts += 1
    job.local_checksum = checksum or job.local_checksum
    job.server_checksum = job.server_checksum  # server blob is immutable per File row
    job.state = (
        "conflict"
        if job.server_checksum and job.local_checksum and job.local_checksum != job.server_checksum
        else "done"
    )
    job.updated_at = utcnow()
    return job


def resolve_conflict(
    db: SAMSession, *, user_id: str, job_id: str, strategy: str
) -> SyncJob:
    if strategy not in VALID_STRATEGIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_strategy"})
    job = owned_job(db, user_id=user_id, job_id=job_id)
    if job.state != "conflict":
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "not_in_conflict"})
    job.conflict_strategy = strategy
    job.state = "done"
    job.updated_at = utcnow()
    _activity(
        db, user_id=user_id, kind="device",
        summary=f"Resolved sync conflict with \u201c{strategy}\u201d",
    )
    return job
