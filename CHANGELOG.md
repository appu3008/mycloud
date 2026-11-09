# Changelog

## 0.2.0 — Phase 2 (2026-11-09)
### Added
- All 20 database entities (`backend/app/models/`, naming-convention-checkable,
  CHECK/UNIQUE/FK constraints per DATABASE.md) + engine factory (WAL, FK ON,
  synchronous=NORMAL on every connect) + health DB probe.
- Alembic wiring (`backend/migrations/`, project-root-anchored URL from settings)
  + initial migration applied: 22 tables in `database/mycloud.db`.
- Argon2id password hashing (OWASP-aligned parameters, transparent rehash), no
  plaintext ever stored.
- Security layer: Hashed-at-rest session cookies, CSRF tokens per session
  (X-CSRF-Token double-submit + Origin check), durable audit-based brute-force
  lockout (5 fails / 15 min per account + 4x per-IP spray guard), first-admin
  enrollment window closed by marker file (mode 0600) after use.
- Auth API (v1): provider/init, login (uniform anti-enumeration error),
  logout, me, profile update, password change (revokes other sessions),
  sessions list + revocation, 90-day login history (no secrets), register
  (closed, honest 403 until Phase 12 invites).
- pytest suite (10 tests, per-test isolated temp DB/storage): passes.

### Verified
- Backend boots against the migrated dev DB; `/api/health` reports WAL mode +
  FK enforced; unauthenticated `/auth/me` = 401; enrollment reports open.
- ruff clean (B008 ignored as the canonical FastAPI idiom).

### Fixed
- Failed-login audit rows now commit inside `authenticate` so lockout/history
  survives 401 request teardown.
- Unflushed user id in first-admin creation caused FK failures; explicit ids
  and a flush make ordering deterministic.
- Relative `MYCLOUD_*` paths and sqlite URLs are resolved against the project
  root (CWD independent); `backend/storage` stray dirs from earlier test boot
  removed.

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

