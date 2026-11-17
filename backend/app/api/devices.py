"""Devices API (v1): registration/trust and sync-job orchestration."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SessionSAM

from ..core.database import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas.devices import (
    BackupConfig,
    DeviceCreate,
    DeviceInfo,
    DeviceList,
    DeviceUpdate,
    SyncJobComplete,
    SyncJobCreate,
    SyncJobInfo,
    SyncJobList,
    SyncJobResolve,
)
from ..services import activity_service, device_service
from .dependencies import csrf_protected_auth, get_current_auth

devices_router = APIRouter(prefix="/devices", tags=["devices"])
sync_router = APIRouter(prefix="/sync", tags=["sync"])


@devices_router.post("", response_model=DeviceInfo, status_code=201)
def register_device(
    body: DeviceCreate,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> DeviceInfo:
    user, _ = auth
    device = device_service.register_device(
        db,
        user_id=user.id,
        name=body.name,
        platform=body.platform,
        public_key=body.public_key,
    )
    db.commit()
    return DeviceInfo(**device_service.device_dict(db, device))


@devices_router.get("", response_model=DeviceList)
def list_devices(
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> DeviceList:
    user, _ = auth
    return DeviceList(items=device_service.list_devices(db, user_id=user.id))


@devices_router.patch("/{device_id}", response_model=DeviceInfo)
def update_device(
    device_id: str,
    body: DeviceUpdate,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> DeviceInfo:
    user, _ = auth
    device = device_service.update_device(
        db,
        user_id=user.id,
        device_id=device_id,
        trust_level=body.trust_level,
        can_sync=body.can_sync,
        can_backup=body.can_backup,
        revoke=body.revoke,
    )
    db.commit()
    return DeviceInfo(**device_service.device_dict(db, device))


@devices_router.post("/{device_id}/heartbeat", response_model=DeviceInfo)
def heartbeat(
    device_id: str,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> DeviceInfo:
    user, _ = auth
    device = device_service.heartbeat(db, user_id=user.id, device_id=device_id)
    db.commit()
    return DeviceInfo(**device_service.device_dict(db, device))


@devices_router.get("/{device_id}/backup-config", response_model=BackupConfig)
def backup_config(
    device_id: str,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> BackupConfig:
    """Instructions a trusted Android backup client uses to stream uploads."""
    user, _ = auth
    return BackupConfig(**device_service.backup_config(db, user_id=user.id, device_id=device_id))


@sync_router.post("/jobs", response_model=SyncJobInfo, status_code=201)
def queue_sync(
    body: SyncJobCreate,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> SyncJobInfo:
    user, _ = auth
    job = device_service.queue_sync(
        db,
        user_id=user.id,
        device_id=body.device_id,
        file_id=body.file_id,
        direction=body.direction,
        local_checksum=body.local_checksum,
        conflict_strategy=body.conflict_strategy,
    )
    activity_service.log_event(
        db, user_id=user.id, kind="device",
        summary=f"Queued {body.direction} sync for file \u201c{body.file_id}\u201d",
    )
    db.commit()
    return SyncJobInfo(**device_service.job_dict(job))


@sync_router.get("/jobs", response_model=SyncJobList)
def list_jobs(
    device_id: str | None = None,
    auth: tuple[User, SessionRow] = Depends(get_current_auth),
    db: SessionSAM = Depends(get_db),
) -> SyncJobList:
    user, _ = auth
    return SyncJobList(items=device_service.list_jobs(db, user_id=user.id, device_id=device_id))


@sync_router.post("/jobs/{job_id}/complete", response_model=SyncJobInfo)
def complete_job(
    job_id: str,
    body: SyncJobComplete,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> SyncJobInfo:
    user, _ = auth
    job = device_service.complete_job(
        db, user_id=user.id, job_id=job_id, checksum=body.checksum
    )
    db.commit()
    return SyncJobInfo(**device_service.job_dict(job))


@sync_router.post("/jobs/{job_id}/resolve", response_model=SyncJobInfo)
def resolve_conflict(
    job_id: str,
    body: SyncJobResolve,
    auth: tuple[User, SessionRow] = Depends(csrf_protected_auth),
    db: SessionSAM = Depends(get_db),
) -> SyncJobInfo:
    user, _ = auth
    job = device_service.resolve_conflict(
        db, user_id=user.id, job_id=job_id, strategy=body.strategy
    )
    db.commit()
    return SyncJobInfo(**device_service.job_dict(job))
