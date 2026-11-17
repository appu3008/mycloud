"""Backup jobs API (v1): create/list/delete jobs, run + inspect backups."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SAMSession

from ..core.config import get_settings
from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas.backups import (
    BackupJobCreate,
    BackupJobInfo,
    BackupJobList,
    BackupRun,
    BackupRunList,
)
from ..services import activity_service, backup_service
from .dependencies import csrf_protected_auth, get_current_auth

router = APIRouter(prefix="/backups", tags=["backups"])


def _require_admin(user: User) -> None:
    if not user.is_admin:
        from fastapi import HTTPException, status

        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail={"error": "admin_required"}
        )


@router.post("/jobs", response_model=BackupJobInfo, status_code=201)
def create_job(
    body: BackupJobCreate,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> BackupJobInfo:
    user, _ = auth
    _require_admin(user)
    job = backup_service.create_job(
        db,
        name=body.name,
        target_path=body.target_path,
        include_content_blobs=body.include_content_blobs,
        retention_count=body.retention_count,
        schedule_cron=body.schedule_cron,
    )
    activity_service.log_event(
        db, user_id=user.id, kind="backup",
        summary=f"Created backup job \u201c{job.name}\u201d",
    )
    db.commit()
    db.refresh(job)
    return BackupJobInfo(
        id=job.id, name=job.name, target_path=job.target_path,
        include_content_blobs=job.include_content_blobs,
        retention_count=job.retention_count, schedule_cron=job.schedule_cron,
        enabled=job.enabled, backup_count=0, created_at=job.created_at,
    )


@router.get("/jobs", response_model=BackupJobList)
def list_jobs(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> BackupJobList:
    user, _ = auth
    _require_admin(user)
    return BackupJobList(
        items=[BackupJobInfo(**item) for item in backup_service.list_jobs(db)]
    )


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> dict:
    user, _ = auth
    _require_admin(user)
    job = backup_service.owned_job(db, job_id)
    backup_service.delete_job(db, job)
    db.commit()
    return {"deleted": job_id}


@router.post("/jobs/{job_id}/run", response_model=BackupRun)
def run_job(
    job_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SAMSession = Depends(get_db),
) -> BackupRun:
    """Run a job now (synchronous). Cron scheduling is not in-process yet."""
    user, _ = auth
    _require_admin(user)
    job = backup_service.owned_job(db, job_id)
    backup = backup_service.run_backup(db, get_settings(), job)
    activity_service.log_event(
        db, user_id=user.id, kind="backup",
        summary=f"Backup \u201c{job.name}\u201d finished: {backup.state}",
    )
    db.commit()
    return BackupRun.model_validate(backup)


@router.get("/jobs/{job_id}/backups", response_model=BackupRunList)
def job_backups(
    job_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SAMSession = Depends(get_db),
) -> BackupRunList:
    user, _ = auth
    _require_admin(user)
    backup_service.owned_job(db, job_id)
    return BackupRunList(
        items=[BackupRun(**row) for row in backup_service.list_backups(db, job_id)]
    )
