"""Hosting app-manager API (v1, admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SessionSAM

from ..core.config import get_settings
from ..core.database import get_db
from ..models import User
from ..schemas.hosting import (
    HostedAppCreate,
    HostedAppInfo,
    HostedAppList,
    HostedAppUpdate,
    StaticFileWrite,
)
from ..services import activity_service, hosting_service
from .dependencies import csrf_protected_user, get_current_user, require_admin

router = APIRouter(prefix="/hosting", tags=["hosting"])


@router.post("/apps", response_model=HostedAppInfo, status_code=201)
def create_app(
    body: HostedAppCreate,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> HostedAppInfo:
    require_admin(actor)
    app = hosting_service.create_app(
        db,
        name=body.name,
        kind=body.kind,
        domain=body.domain,
        path_prefix=body.path_prefix,
        upstream_port=body.upstream_port,
        description=body.description,
        settings=get_settings(),
    )
    activity_service.log_event(
        db, user_id=actor.id, kind="admin",
        summary=f"Registered hosted app \u201c{app.name}\u201d",
    )
    db.commit()
    return HostedAppInfo(**hosting_service.app_dict(app))


@router.get("/apps", response_model=HostedAppList)
def list_apps(
    _: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> HostedAppList:
    return HostedAppList(items=hosting_service.list_apps(db))


@router.patch("/apps/{app_id}", response_model=HostedAppInfo)
def update_app(
    app_id: str,
    body: HostedAppUpdate,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> HostedAppInfo:
    require_admin(actor)
    app = hosting_service.update_app(
        db, app_id, enabled=body.enabled, description=body.description
    )
    db.commit()
    return HostedAppInfo(**hosting_service.app_dict(app))


@router.delete("/apps/{app_id}")
def delete_app(
    app_id: str,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> dict:
    require_admin(actor)
    result = hosting_service.delete_app(db, app_id)
    db.commit()
    return result


@router.post("/config/stage")
def stage_config(
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> dict:
    """Stage the generated nginx config — never touches /etc/nginx."""
    require_admin(actor)
    return hosting_service.stage_config(db, get_settings())


@router.get("/config/preview")
def preview_config(
    _: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> dict:
    return {"config": hosting_service.generate_config(db)}


@router.get("/apps/{app_id}/files")
def static_files(
    app_id: str,
    _: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> dict:
    return {"items": hosting_service.list_static_files(db, app_id)}


@router.put("/apps/{app_id}/files")
def write_static_file(
    app_id: str,
    body: StaticFileWrite,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> dict:
    require_admin(actor)
    result = hosting_service.write_static_file(db, app_id, body.path, body.content)
    db.commit()
    return result
