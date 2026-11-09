# MyCloud

Self-hosted personal cloud storage and device management. Your source code, your
storage engine, your database, your server. Python 3.14 / FastAPI / SQLAlchemy 2 /
SQLite (WAL) backend, React + TypeScript + Vite frontend, Argon2id auth,
content-addressed deduplicating storage with versioning and soft deletion.

## Quickstart (development)
```bash
cd ~/mycloud
python3 scripts/generate_secret.py          # paste MYCLOUD_SECRET_KEY into .env
cp .env.example .env
python3 -m venv backend/.venv               # dependency plan approved first
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
# http://127.0.0.1:8000/api/health
```
Frontend lands in Phase 4 (`~/mycloud/frontend`).

## Status — phases
| # | Phase | State |
|---|---|---|
| 1 | Foundation: env report, scaffold, docs | **done** |
| 2 | Database models + auth (Argon2id, sessions, CSRF) | **done** |
| 3 | Storage engine (chunked resumable uploads, blobs) | in progress |
| 4 | File manager frontend | pending |
| 5 | Photo/video system | pending |
| 6 | Recycle bin + versioning | pending |
| 7 | Duplicate detection | pending |
| 8 | Sharing | pending |
| 9 | Devices + sync | pending |
| 10 | Android backup client path | pending |
| 11 | Storage analytics + monitoring | pending |
| 12 | Administration + activity | pending |
| 13 | Optional E2E encryption | pending |
| 14 | Backup/recovery jobs | pending |
| 15 | Security test suite | pending |
| 16 | Remote connectivity (Tailscale) | pending |
| 17 | Production deployment | pending |

Docs: `ARCHITECTURE.md` · `DATABASE.md` · `API.md` · `SECURITY.md` ·
`DEPLOYMENT.md` · `BACKUP_AND_RESTORE.md` · `CHANGELOG.md` · `docs/`.
