#!/usr/bin/env python3
"""Phase 1 environment inspection report (spec section 27).

Reads real system values only; no network calls. Run:
    python3 scripts/env_report.py
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path


def run(cmd: str) -> str:
    try:
        out = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=10)
        return (out.stdout.strip() or out.stderr.strip() or "(none)")
    except FileNotFoundError:
        return "(not installed)"
    except Exception as exc:  # noqa: BLE001
        return f"(error: {exc})"


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    usage = shutil.disk_usage(root)

    rows = [
        ("OS", f"{platform.system()} ({platform.freedesktop_os_release().get('PRETTY_NAME', '?')})"),
        ("Kernel", platform.release()),
        ("Machine", platform.machine()),
        ("Python", sys.version.split()[0]),
        ("CPU", os.cpu_count() or 0),
        ("RAM total MB", os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 1024 // 1024),
        ("Node", run("node --version")),
        ("npm", run("npm --version")),
        ("Git", run("git --version")),
        ("Disk path", str(root)),
    ]
    print("== MyCloud environment report ==")
    for key, value in rows:
        print(f"{key:12} {value}")
    print(f"{'Disk':12} total {usage.total // 2**30} GB, free {usage.free // 2**30} GB "
          f"({usage.used / usage.total * 100:.1f}% used)")
    print(f"{'Storage':12} {run('lsblk -d -n -o SIZE')[:0] or '(see lsblk)'}")
    try:
        gateway = socket.gethostbyname(socket.gethostname())
    except Exception:  # noqa: BLE001
        gateway = "(unknown)"
    print(f"{'Hostname':12} {socket.gethostname()} ({gateway})")


if __name__ == "__main__":
    main()
