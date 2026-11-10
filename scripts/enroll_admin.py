#!/usr/bin/env python3
"""Interactive first-admin enrollment (run while the backend is online).

Prompts for email, display name and password with getpass() so the password
never appears in shell history, command lines, or logs.

Usage:
    python scripts/enroll_admin.py [port]        # default port 8000
"""

from __future__ import annotations

import getpass
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    url = f"http://127.0.0.1:{port}/api/v1/auth/provider/init"
    status_url = f"http://127.0.0.1:{port}/api/v1/auth/provider/init/status"

    # Refuse if enrollment is closed (server running).
    try:
        status = json.load(urllib.request.urlopen(status_url, timeout=5))
    except urllib.error.URLError as exc:
        print(f"Backend not reachable on port {port} ({exc.reason}). Start it first:")
        print("  cd ~/mycloud/backend && .venv/bin/uvicorn app.main:app --port 8000")
        return 1
    if not status.get("enrollment_open"):
        print(f"Enrollment closed: {status.get('reason')}. An admin already exists.")
        return 1

    email = input("Admin email: ").strip()
    display_name = input("Display name: ").strip()
    while True:
        password = getpass.getpass("Password (min 10 chars, letters+digits): ")
        password2 = getpass.getpass("Repeat password: ")
        if password != password2:
            print("Mismatch; try again.\n")
            continue
        if len(password) < 10 or password.isalpha() or password.isdigit():
            print("At least 10 characters, with letters AND digits.\n")
            continue
        break

    body = json.dumps(
        {"email": email, "display_name": display_name, "password": password}
    ).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
        payload = json.load(response)
        csrf = payload.get("csrf_token", "")[:8] + "…"
        user = payload.get("user", {})
        print()
        print(f"Admin enrolled: {user.get('email')} (role={user.get('role')})")
        print(f"Session cookie set; CSRF token issued ({csrf}).")
        print("Keep this password safe; it is the only way into this account.")
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        print(f"Enrollment refused ({exc.code}): {detail}")
        print("If enrollment is already used, this is permanent by design.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
