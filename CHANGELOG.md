# Changelog

## 0.1.0 — Phase 1 (2026-11-09)
### Fixed
- `cors_origins` env parsing: annotated with `pydantic-settings` `NoDecode` and a
  before-validator so the env may be JSON array or comma-separated.

### Verified with dependencies installed
- Backend venv (Python 3.14): FastAPI 0.162.2, SQLAlchemy 2.1.8, Alembic 1.20.1,
  argon2-cffi 25.1.0, pydantic-settings 2.16.2, python-multipart, pytest 8.4.2,
  pytest-asyncio, uvicorn 0.54.0 (uvloop/watchfiles extras), ruff — lint clean.
- Frontend: create-vite 9.3.4 React-TS; production build `npm run build` passes
  (222 KB JS / 69 KB gzip); 0 npm vulnerabilities.
- Live boot test: `/api/health` returned `status ok` with real disk telemetry
  (186 GB free) and no storage errors; `/api/health/ping` OK.
- `app.main` imports cleanly incl. routes `/api/health`, `/api/health/ping`.

### Added (deployment/owner actions pending)
- `scripts/mount_storage_partition.sh` (user runs with sudo) to mount the unused
  ext4 partition `/dev/nvme0n1p7` (UUID 267bb988...) at `/mnt/mycloud-storage`
  with `noexec,nosuid,nodev`; refuses to proceed if partition is non-empty.
  `deployment/fstab-entry.example` provided for persistence.

### Added
- Project scaffold: backend modular tree (api/core/models/schemas/services/
  repositories/security/storage/workers), storage/data/backup directories,
  frontend and migrations placeholders.
- `FastAPI` application skeleton: configurable settings (`MYCLOUD_*` env),
  dev-loopback binding enforcement, CORS+gzip middleware, real `/api/health`
  (storage dirs, disk capacity, environment) and `/api/health/ping`.
- Documentation set: ARCHITECTURE, DATABASE (20 entities), API (v1 design),
  SECURITY (threat model), DEPLOYMENT (systemd/proxy/Tailscale/NAT),
  BACKUP_AND_RESTORE, docs/ENVIRONMENT.md (inspection report), docs/ROADMAP.md.
- Scripts: `scripts/env_report.py`, `scripts/generate_secret.py`.
- `.env.example`, `.gitignore`, `backend/requirements.txt`, example systemd unit,
  (inert) docker-compose.yml for when Docker is available.

### Verified
- Environment inspection (see docs/ENVIRONMENT.md): Kali 2026.3, Python 3.14.8,
  Node 22.18, 187 GB free on root, no existing mycloud repo (fresh build).
- `python3 -m py_compile` pass on all backend files.

