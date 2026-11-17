"""Own-network auditing: authorized, local-only port scans + hardening checks.

Every scan must name an active ScanScope, the target must be inside that
CIDR, and both scope and target must be non-public address space. No
credentials are tested and no exploit payloads are sent: this is inventory,
not offense. Each scan is written to the audit log by the API layer.
"""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as SAMSession

from ..models import BackupJob, NetworkScan, ScanFinding, ScanScope, User, new_id, utcnow

COMMON_PORTS = (22, 23, 80, 443, 8000, 8080, 3000, 5000, 3306, 5432, 6379, 3389, 27017)
SERVICES = {
    22: "ssh", 23: "telnet", 80: "http", 443: "https",
    8000: "http-alt", 8080: "http-proxy", 3000: "dev-app", 5000: "dev-app",
    3306: "mysql", 5432: "postgresql", 6379: "redis",
    3389: "rdp", 27017: "mongodb",
}
HIGH_RISK = {23, 3306, 5432, 6379, 3389, 27017}
MEDIUM_RISK = {22}


def _private(address: ipaddress._BaseAddress) -> bool:
    return not address.is_global and (
        address.is_private or address.is_loopback or address.is_link_local
    )


def create_scope(
    db: SAMSession,
    *,
    user_id: str,
    name: str,
    cidr: str,
    authorized_hours: int | None,
    notes: str,
) -> ScanScope:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_cidr"}) from exc
    if network.version != 4 or not _private(network.network_address):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "scope_must_be_private"}
        )
    if not name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_name"})
    exists = db.execute(
        select(ScanScope).where(ScanScope.cidr == str(network))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "scope_exists"})
    scope = ScanScope(
        id=new_id(),
        name=name.strip()[:128],
        cidr=str(network),
        owner_user_id=user_id,
        authorized_until=(
            utcnow() + timedelta(hours=authorized_hours) if authorized_hours else None
        ),
        enabled=True,
        notes=notes[:2000],
        created_at=utcnow(),
    )
    db.add(scope)
    return scope


def owned_scope(db: SAMSession, user_id: str, scope_id: str) -> ScanScope:
    scope = db.get(ScanScope, scope_id)
    if scope is None or scope.owner_user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "scope_not_found"})
    return scope


def scope_dict(scope: ScanScope) -> dict:
    return {
        "id": scope.id,
        "name": scope.name,
        "cidr": scope.cidr,
        "authorized_until": scope.authorized_until,
        "enabled": scope.enabled,
        "notes": scope.notes,
        "created_at": scope.created_at,
    }


def list_scopes(db: SAMSession, *, user_id: str) -> list[dict]:
    rows = db.execute(
        select(ScanScope).where(ScanScope.owner_user_id == user_id).order_by(ScanScope.name)
    ).scalars().all()
    return [scope_dict(row) for row in rows]


def disable_scope(db: SAMSession, *, user_id: str, scope_id: str) -> dict:
    scope = owned_scope(db, user_id, scope_id)
    scope.enabled = False
    return {"disabled": scope_id}


def _port_open(target: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((target, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_scan(
    db: SAMSession,
    *,
    user_id: str,
    scope_id: str,
    target: str,
    ports: list[int] | None,
    initiated_by: str,
) -> dict:
    scope = owned_scope(db, user_id, scope_id)
    if not scope.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "scope_disabled"})
    if scope.authorized_until and scope.authorized_until < utcnow():
        raise HTTPException(status.HTTP_410_GONE, detail={"error": "scope_expired"})

    try:
        address = ipaddress.ip_address(target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_target"}) from exc
    if address.version != 4 or not _private(address):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "public_target_rejected"}
        )
    if address not in ipaddress.ip_network(scope.cidr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "target_outside_scope"})

    selected = list(dict.fromkeys(ports or COMMON_PORTS))[:50]
    if any(not 1 <= port <= 65535 for port in selected):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_port"})

    scan = NetworkScan(
        id=new_id(), scope_id=scope.id, target=target,
        ports=",".join(str(port) for port in selected), state="running",
        findings_count=0, initiated_by=initiated_by, started_at=utcnow(),
    )
    db.add(scan)
    db.flush()

    open_ports: list[int] = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(_port_open, target, port, 0.3): port for port in selected}
        for future in as_completed(futures):
            if future.result():
                open_ports.append(futures[future])
    open_ports.sort()

    created_findings: list[dict] = []
    for port in open_ports:
        service = SERVICES.get(port, "unknown")
        if port in HIGH_RISK:
            severity, advice = "high", "Restrict to trusted hosts or disable if unused"
        elif port in MEDIUM_RISK:
            severity, advice = "medium", "Prefer key-based auth and firewall rules"
        else:
            severity, advice = "low", "Verify this service is intentional"
        finding = ScanFinding(
            id=new_id(), scan_id=scan.id, port=port, service=service,
            severity=severity, summary=f"{service} listening: {advice}",
        )
        db.add(finding)
        created_findings.append(
            {
                "id": finding.id,
                "port": port,
                "service": service,
                "severity": severity,
                "summary": finding.summary,
            }
        )

    scan.state = "completed"
    scan.findings_count = len(open_ports)
    scan.finished_at = utcnow()
    return {"scan": scan_dict(scan), "findings": created_findings}


def scan_dict(scan: NetworkScan) -> dict:
    return {
        "id": scan.id,
        "scope_id": scan.scope_id,
        "target": scan.target,
        "ports": scan.ports,
        "state": scan.state,
        "findings_count": scan.findings_count,
        "initiated_by": scan.initiated_by,
        "started_at": scan.started_at,
        "finished_at": scan.finished_at,
    }


def list_scans(db: SAMSession, *, user_id: str) -> list[dict]:
    rows = db.execute(
        select(NetworkScan)
        .join(ScanScope, NetworkScan.scope_id == ScanScope.id)
        .where(ScanScope.owner_user_id == user_id)
        .order_by(NetworkScan.started_at.desc())
        .limit(100)
    ).scalars().all()
    return [scan_dict(row) for row in rows]


def scan_report(db: SAMSession, *, user_id: str, scan_id: str) -> dict:
    scan = db.get(NetworkScan, scan_id)
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "scan_not_found"})
    owned_scope(db, user_id, scan.scope_id)
    findings = db.execute(
        select(ScanFinding).where(ScanFinding.scan_id == scan.id).order_by(ScanFinding.port)
    ).scalars().all()
    return {
        "scan": scan_dict(scan),
        "findings": [
            {
                "id": row.id,
                "port": row.port,
                "service": row.service,
                "severity": row.severity,
                "summary": row.summary,
            }
            for row in findings
        ],
    }


def hardening_checks(db: SAMSession, settings) -> list[dict]:
    """Local posture checks — no network calls, no secrets in output."""
    from ..core.database import database_status

    admins = len(
        db.execute(
            select(User).where(User.is_admin.is_(True), User.is_active.is_(True))
        ).scalars().all()
    )
    jobs = db.execute(select(BackupJob)).scalars().all()
    db_status = database_status()
    wildcard_cors = any(origin.strip() == "*" for origin in settings.cors_origins)

    def item(check_id: str, title: str, ok: bool, detail: str) -> dict:
        return {
            "id": check_id,
            "title": title,
            "status": "ok" if ok else "warn",
            "detail": detail,
        }

    return [
        item(
            "production_env",
            "Production environment configured",
            settings.environment == "production",
            f"current environment: {settings.environment}",
        ),
        item(
            "secret_key",
            "Strong secret key set",
            len(settings.secret_key) >= 32,
            "MYCLOUD_SECRET_KEY should be at least 32 characters",
        ),
        item(
            "cors",
            "CORS locked to explicit origins",
            not wildcard_cors,
            "Wildcard origins must not be used in production",
        ),
        item(
            "admin_count",
            "Limited admin accounts",
            1 <= admins <= 3,
            f"{admins} active admin account(s)",
        ),
        item(
            "backups",
            "Backup job configured",
            len(jobs) > 0,
            f"{len(jobs)} backup job(s)",
        ),
        item(
            "database",
            "Database reachable",
            db_status.get("status") == "ok",
            str(db_status.get("status")),
        ),
    ]
