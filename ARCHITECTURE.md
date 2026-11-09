# MyCloud — Architecture

Version: 0.1.0 · Phase 1 foundation

## 1. System overview

MyCloud is a self-hosted personal cloud storage + device management platform.

```
Android phone / other devices            Laptop (Kali Linux, the server)
+------------------+                     +---------------------------------------+
| MyCloud client   |   HTTPS (Tailscale  |  Reverse proxy (TLS)                  |
| web app / APK    |   or home LAN) ---->|        |                              |
+------------------+                     |  FastAPI backend (uvicorn)            |
                                         |        |      SQLAlchemy              |
                                         |  Storage engine --- filesystem blobs  |
                                         |        |                              |
                                         |  SQLite (WAL) / future PostgreSQL     |
                                         +---------------------------------------+
```

Key decision: the **application layer is transport-independent**. The backend always
binds loopback; any access path (LAN, Tailscale, future custom VPN) terminates at the
reverse proxy, which owns TLS.

## 2. Layers

| Layer | Responsibility | Location |
|---|---|---|
| API routers | HTTP in/out, validation, status codes | `backend/app/api/` |
| Schemas | Pydantic request/response models | `backend/app/schemas/` |
| Services | Business logic (uploads, versioning, sharing, sync) | `backend/app/services/` |
| Repositories | DB access with **ownership checks baked in** (anti-IDOR) | `backend/app/repositories/` |
| Models | SQLAlchemy ORM entities | `backend/app/models/` |
| Security | Argon2id, sessions, CSRF, rate limiting, authorization | `backend/app/security/` |
| Storage engine | Content-addressed blob store, chunk assembler, thumbnails | `backend/app/storage/` |
| Workers | Retention, version cleanup, backup jobs, FTS index | `backend/app/workers/` |

Rules enforced across layers:
- Services never trust client IDs: every repository query filters by `owner_id`.
- Requests never name files: blobs are addressed by SHA-256 and DB-issued UUIDs.
- Streaming everywhere: chunked uploads and range downloads never buffer whole files in RAM.

## 3. Storage engine design

```
storage/
  files/aa/ab/<sha256-hex>.blob      # immutable content, addressed by SHA-256
  thumbnails/aa/ab/<blob-hash>-s.jpg # re-encoded derivatives only
  temporary/<upload-uuid>/           # in-flight chunks: 00001.part, 00002.part ...
```

- `files` and `file_versions` logical entities reference `content_blobs` by hash.
- `content_blobs.ref_count` = number of logical references. A blob is deleted **only**
  when no references remain (dup detection + multi-user shared content is safe).
- Upload flow: `POST /api/v1/uploads` (reserve) -> `PUT .../chunks/{n}` (per-chunk
  SHA-256 checksum, dedup-aware) -> `POST .../complete` (assemble -> final SHA-256 ->
  store -> DB transaction -> temp cleanup). Interrupted uploads resume with
  `GET /api/v1/uploads/{id}` state; stale temp dirs are garbage-collected by a worker.

## 4. Entity relationship diagram

```
users 1---* sessions            users 1---* devices          users 1---* folders
users 1---* files               users 1---* favorites        users 1---* albums
users 1---* notifications       users 1---* shares           users 1---* activity_events
users 1---1 storage_quotas

folders 1---* folders          (parent_id, self-referencing tree)
folders 1---1 folders.parent (recursive)

files *---1 folders             files *---1 content_blobs
files 1---* file_versions       file_versions *---1 content_blobs
files 1---1 media_metadata     (photos/videos only)
files 1---* favorites
files *---* albums             (album_files join)
files 1---* sync_jobs
files 1---* shares

uploads 1---* upload_chunks    uploads *---1 users, uploads *---1 folders (target)
uploads *---1 content_blobs?   (set when final hash dedups to an existing blob)

backups *---1 backup_jobs       devices 1---* sessions (device-bound sessions)
audit_logs (system events, actor nullable)   activity_events (user-visible actions)
```

## 5. Background work

Phase-appropriate scheduling via workers (asyncio background tasks initially;
systemd-timed or Celery-like split can be revisited later — no RabbitMQ dependency):
- retention sweeper (recycle bin + expired versions + temp GC) — hourly
- thumbnail queue — on-demand with work queue
- backup job runner — scheduled output to `backups/` and configured destinations

## 6. Failure handling

- All filesystem mutations happen inside DB transactions that commit *after* blob
  placement, so a crash cannot leave a DB row pointing at missing bytes.
- Orphan-sweep worker reconciles temp dirs and reference counts on startup.
