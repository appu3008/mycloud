# Changelog

## 0.1.0 — Phase 1 (2026-11-09)
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
