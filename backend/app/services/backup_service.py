"""Backup / recovery service: jobs, backup runs, verification, pruning.

A backup run produces a self-contained folder:
  <target>/<timestamp>-<name>/
    mycloud.db     consistent SQLite snapshot (online backup API)
    blobs/...      physical blob files (when include_content_blobs)
    manifest.json  db + blob inventory, hashed for verification

Verification re-checks stored blobs against the manifest. Pruning keeps
only the newest ``retention_count`` run directories per job. Cron strings
are stored for documentation but nothing executes them in-process yet;
jobs are run manually (API button or systemd timer) and the UI says so.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SAMSession

from ..core.config import PROJECT_ROOT, Settings
from ..models import Backup, BackupJob, ContentBlob, new_id, utcnow
from ..storage import blob_store


class BackupError(HTTPException):
    def __init__(self, code: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail={"error": code})


def _sanitize(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip()
    return cleaned[:80] or "backup-job"


def _resolve_target(settings: Settings, target_path: str) -> Path:
    base = Path(target_path)
    if not base.is_absolute():
        base = PROJECT_ROOT / base
    return base


def create_job(
    db: SAMSession,
    *,
    name: str,
    target_path: str | None,
    include_content_blobs: bool,
    retention_count: int,
    schedule_cron: str | None = None,
) -> BackupJob:
    job = BackupJob(
        id=new_id(),
        name=_sanitize(name),
        target_path=target_path or "data/backups",
        include_content_blobs=include_content_blobs,
        retention_count=max(1, min(retention_count, 50)),
        schedule_cron=schedule_cron or None,
        enabled=True,
        created_at=utcnow(),
    )
    db.add(job)
    return job


def owned_job(db: SAMSession, job_id: str) -> BackupJob:
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"error": "job_not_found"}
        )
    return job


def delete_job(db: SAMSession, job: BackupJob) -> None:
    db.delete(job)


def list_jobs(db: SAMSession) -> list[dict]:
    rows = db.execute(
        select(BackupJob).order_by(BackupJob.created_at.asc())
    ).scalars().all()
    counts: dict[str, int] = {
        job_id: int(count)
        for job_id, count in db.execute(
            select(Backup.job_id, func.count()).group_by(Backup.job_id)
        ).all()
    }
    return [
        {
            "id": job.id,
            "name": job.name,
            "target_path": job.target_path,
            "include_content_blobs": job.include_content_blobs,
            "retention_count": job.retention_count,
            "schedule_cron": job.schedule_cron,
            "enabled": job.enabled,
            "backup_count": counts.get(job.id, 0),
            "created_at": job.created_at,
        }
        for job in rows
    ]


def list_backups(db: SAMSession, job_id: str) -> list[dict]:
    rows = db.execute(
        select(Backup)
        .where(Backup.job_id == job_id)
        .order_by(Backup.started_at.desc())
    ).scalars().all()
    return [_backup_dict(row) for row in rows]


def _backup_dict(row: Backup) -> dict:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "size_bytes": row.size_bytes,
        "state": row.state,
        "destination": row.destination,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def run_backup(db: SAMSession, settings: Settings, job: BackupJob) -> Backup:
    """Execute a job synchronously; the backup row records the outcome."""
    db_path = settings.database_url.removeprefix("sqlite:///")
    if not Path(db_path).is_file():
        raise BackupError("database_missing")

    timestamp = utcnow().strftime("%Y%m%d-%H%M%S")
    destination = (
        _resolve_target(settings, job.target_path)
        / f"{timestamp}-{_sanitize(job.name).replace(' ', '-')}"
    )
    destination.mkdir(parents=True, exist_ok=True)

    backup = Backup(
        id=new_id(),
        job_id=job.id,
        manifest_sha256="",
        content_sha256="",
        size_bytes=0,
        state="running",
        destination=str(destination),
        started_at=utcnow(),
    )
    db.add(backup)

    try:
        size = _write_snapshot(db, settings, job, destination, db_path)
        manifest_bytes = (destination / "manifest.json").read_bytes()
        backup.manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        backup.content_sha256 = json.loads(manifest_bytes)["content_sha256"]
        backup.size_bytes = size
        backup.state = "verified"
    except HTTPException:
        backup.state = "failed"
        backup.finished_at = utcnow()
        (destination / "error.txt").write_text("backup failed", encoding="utf-8")
        raise
    except Exception as exc:  # noqa: BLE001 - the row records its own failure
        backup.state = "failed"
        backup.finished_at = utcnow()
        (destination / "error.txt").write_text(str(exc), encoding="utf-8")
        raise BackupError("backup_failed") from exc

    backup.finished_at = utcnow()
    _prune_old_backups(job, destination.parent)
    return backup


def _write_snapshot(
    db: SAMSession,
    settings: Settings,
    job: BackupJob,
    destination: Path,
    db_path: str,
) -> int:
    """Dump the DB, copy blobs when asked, write manifest.json; total bytes."""
    # 1. Consistent online snapshot of the SQLite database.
    dest_db = destination / "mycloud.db"
    source = sqlite3.connect(db_path)
    try:
        target = sqlite3.connect(dest_db)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    total = dest_db.stat().st_size

    # 2. Physical blob copies (manifest records everything regardless).
    blob_entries: list[dict] = []
    rows = db.execute(select(ContentBlob)).scalars().all()
    for blob in rows:
        source_path = blob_store.blob_abs_path(settings, blob.sha256)
        present = source_path.is_file()
        if present and job.include_content_blobs:
            rel = blob_store.blob_relpath(blob.sha256)
            target_path = destination / "blobs" / rel
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            total += target_path.stat().st_size
        blob_entries.append(
            {
                "sha256": blob.sha256,
                "size_bytes": blob.size_bytes,
                "ref_count": blob.ref_count,
                "present": present,
            }
        )

    # 3. Manifest: inventory + content digest over the inventory.
    manifest = {
        "blobs": blob_entries,
        "include_content_blobs": job.include_content_blobs,
        "database_bytes": dest_db.stat().st_size,
    }
    digest_input = json.dumps(manifest, sort_keys=True).encode() + b"".join(
        entry["sha256"].encode() for entry in blob_entries
    )
    manifest["content_sha256"] = hashlib.sha256(digest_input).hexdigest()
    (destination / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True).encode()
    )
    return total


def _prune_old_backups(job: BackupJob, base: Path) -> None:
    """Keep the newest retention_count run directories for this job."""
    suffix = f"-{_sanitize(job.name).replace(' ', '-')}"
    runs = sorted(
        (p for p in base.iterdir() if p.is_dir() and p.name.endswith(suffix)),
        key=lambda p: p.name,
        reverse=True,
    )
    for stale in runs[job.retention_count:]:
        shutil.rmtree(stale, ignore_errors=True)


def verify_backup(destination: str) -> dict:
    """Re-verify a stored backup against its manifest (recovery dry-run)."""
    manifest_path = Path(destination) / "manifest.json"
    if not manifest_path.is_file():
        raise BackupError("manifest_missing")
    manifest = json.loads(manifest_path.read_text())
    missing = [entry["sha256"] for entry in manifest["blobs"] if not entry["present"]]
    body = dict(manifest)
    body.pop("content_sha256", None)
    digest_input = json.dumps(body, sort_keys=True).encode() + b"".join(
        entry["sha256"].encode() for entry in manifest["blobs"]
    )
    recomputed = hashlib.sha256(digest_input).hexdigest()
    recorded = manifest.get("content_sha256")
    return {
        "ok": not missing and recomputed == recorded,
        "blobs": len(manifest["blobs"]),
        "missing": missing[:20],
        "content_sha256": recorded,
    }
