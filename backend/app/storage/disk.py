"""Disk capacity guardrails (spec section 15): never auto-consume the disk.

Refusal decisions only — the platform never deletes user files to free space.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.config import Settings


@dataclass(frozen=True)
class DiskAllowance:
    ok: bool
    reason: str
    free_bytes: int
    total_bytes: int


def check_write_allowed(settings: Settings, needed_bytes: int = 0) -> DiskAllowance:
    usage = __import__("shutil").disk_usage(str(settings.files_dir))
    used_pct = usage.used / usage.total * 100 if usage.total else 0
    free_after = usage.free - needed_bytes

    if used_pct >= settings.disk_usage_limit_pct:
        return DiskAllowance(
            ok=False,
            reason=f"disk at {used_pct:.1f}%, limit {settings.disk_usage_limit_pct}%",
            free_bytes=usage.free,
            total_bytes=usage.total,
        )
    if free_after < settings.min_free_space_mb * 1024 * 1024:
        return DiskAllowance(
            ok=False,
            reason=(
                f"below reserve: would leave {free_after // 1024 // 1024} MB free, "
                f"minimum {settings.min_free_space_mb} MB"
            ),
            free_bytes=usage.free,
            total_bytes=usage.total,
        )
    return DiskAllowance(ok=True, reason="ok", free_bytes=usage.free, total_bytes=usage.total)


def snapshot(settings: Settings) -> dict:
    """Facts for storage/analytics endpoints (real numbers only)."""
    check = check_write_allowed(settings)
    return {
        "free_bytes": check.free_bytes,
        "total_bytes": check.total_bytes,
        "used_percent": round(
            (check.total_bytes - check.free_bytes) / check.total_bytes * 100, 2
        )
        if check.total_bytes
        else 0.0,
        "write_allowed": check.ok,
        "write_refusal_reason": None if check.ok else check.reason,
    }
