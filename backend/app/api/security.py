"""Own-network auditing API (v1, admin only). Local/private targets only."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SessionSAM

from ..core.config import get_settings
from ..core.database import get_db
from ..models import User
from ..schemas.security import (
    HardeningList,
    ScanCreate,
    ScanList,
    ScanResult,
    ScopeCreate,
    ScopeList,
)
from ..security.audit import record_audit
from ..services import security_service
from .dependencies import csrf_protected_user, get_current_user, require_admin

router = APIRouter(prefix="/security", tags=["security"])


@router.post("/scopes", status_code=201)
def create_scope(
    body: ScopeCreate,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> dict:
    require_admin(actor)
    scope = security_service.create_scope(
        db,
        user_id=actor.id,
        name=body.name,
        cidr=body.cidr,
        authorized_hours=body.authorized_hours,
        notes=body.notes,
    )
    record_audit(
        db,
        action="security.scope.created",
        actor_user_id=actor.id,
        actor_email=actor.email,
        target_type="scan_scope",
        target_id=scope.id,
        detail={"cidr": scope.cidr},
    )
    db.commit()
    return security_service.scope_dict(scope)


@router.get("/scopes", response_model=ScopeList)
def list_scopes(
    actor: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> ScopeList:
    return ScopeList(items=security_service.list_scopes(db, user_id=actor.id))


@router.post("/scopes/{scope_id}/disable")
def disable_scope(
    scope_id: str,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> dict:
    require_admin(actor)
    result = security_service.disable_scope(db, user_id=actor.id, scope_id=scope_id)
    record_audit(
        db,
        action="security.scope.disabled",
        actor_user_id=actor.id,
        actor_email=actor.email,
        target_type="scan_scope",
        target_id=scope_id,
    )
    db.commit()
    return result


@router.post("/scans", response_model=ScanResult, status_code=201)
def run_scan(
    body: ScanCreate,
    actor: User = Depends(csrf_protected_user),
    db: SessionSAM = Depends(get_db),
) -> ScanResult:
    require_admin(actor)
    result = security_service.run_scan(
        db,
        user_id=actor.id,
        scope_id=body.scope_id,
        target=body.target,
        ports=body.ports,
        initiated_by=actor.id,
    )
    record_audit(
        db,
        action="security.scan.completed",
        actor_user_id=actor.id,
        actor_email=actor.email,
        target_type="network_scan",
        target_id=result["scan"]["id"],
        detail={"target": body.target, "findings": result["scan"]["findings_count"]},
    )
    db.commit()
    return ScanResult(**result)


@router.get("/scans", response_model=ScanList)
def list_scans(
    actor: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> ScanList:
    return ScanList(items=security_service.list_scans(db, user_id=actor.id))


@router.get("/scans/{scan_id}", response_model=ScanResult)
def scan_report(
    scan_id: str,
    actor: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> ScanResult:
    return ScanResult(**security_service.scan_report(db, user_id=actor.id, scan_id=scan_id))


@router.get("/hardening", response_model=HardeningList)
def hardening(
    _: User = Depends(require_admin),
    db: SessionSAM = Depends(get_db),
) -> HardeningList:
    return HardeningList(items=security_service.hardening_checks(db, get_settings()))
