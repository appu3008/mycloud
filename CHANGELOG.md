# Changelog

## 0.17.0 — Same-origin CSRF fix (2026-11-17)
### Fixed
- Mutating requests from the app's own origin (e.g. `http://127.0.0.1:8000`)
  were rejected with `origin_forbidden` because the origin check only trusted
  the CORS allow-list (default `127.0.0.1:5173`). Same-origin requests are now
  accepted based on the actual scheme/Host; cross-origin remains restricted
  to explicitly configured origins.

### Verified
- `pytest`: 119 passed, 1 skipped (new same-origin/foreign-origin test).


## 0.16.0 — All-in-one: hosting app manager + own-network auditing (2026-11-17)
### Added
- Hosting app manager (admin only): register static or proxy apps with
  domain/path/port validation, enable/disable/delete, a small safe static
  file writer, nginx config preview and user-owned config staging. Applying
  config is an explicit sudo step (`deployment/apply-hosting.sh.example`);
  the server never touches /etc/nginx.
- Alembic migration `2c9f1a7b3d64` for `hosted_apps`, `scan_scopes`,
  `network_scans`, `scan_findings` (verified: `alembic upgrade head`).
- Security Lab (admin only): written authorization scopes (private CIDRs,
  optional expiry, revocation), bounded TCP inventory scans restricted to
  private targets inside an active scope, severity-labeled findings, scan
  history and a real-config hardening checklist. Every action is audited.
- Hosting and Security pages linked from Settings (Figma nav unchanged).

### Fixed
- E2E vault AES-GCM calls previously passed the algorithm object as the
  *data* argument; encryption now passes plaintext with a proper AesGcmParams
  algorithm object and decryption passes the envelope ciphertext.

### Verified
- `pytest`: 118 passed, 1 skipped; wasm check + trunk build green;
  `/hosting` and `/security` screenshot-verified dark.


## 0.15.0 — Remote connectivity + single-origin production serving (2026-11-17)
### Added
- Backend serves the built Yew app from the same origin via a 404 fallback
  that preserves API 404/405 semantics; one reverse-proxy/Tailscale target
  now serves both the API and client routes (`/share/{token}`, etc.).
- `docs/REMOTE_ACCESS.md`: Tailscale Serve and nginx runbooks, CGNAT guidance,
  production checklist and verification commands.
- `deployment/nginx-mycloud.conf.example` (TLS/HSTS/CSP + loopback proxy) and
  `deployment/tailscale-serve.sh.example` (private tailnet-only exposure).

### Verified
- `pytest`: 110 passed, 1 skipped (no CSS asset in this build); new SPA tests
  cover client routes and API route precedence. No host network state changed.


## 0.14.0 — Security suite + optional E2E vault (2026-11-17)
### Added
- Consolidated security regression suite (9 tests): hashed session/share
  tokens at rest, Argon2id password hashes, CSRF on all newer mutations,
  RBAC on admin/backup APIs, ownership isolation across versions/media/
  albums/devices/shares, injection-like names as literal data, and revoked
  share behavior.
- Optional client-side E2E vault (Settings): PBKDF2-SHA-256 (250k) ->
  AES-256-GCM encryption in WebCrypto before upload; `.vault` envelope
  `MYCE1 | salt | iv | ciphertext`; decrypt-and-download in the browser.
  Passphrase/plaintext never reach the server. `docs/E2E_VAULT.md` documents
  scope and limitations (no key recovery, metadata still visible).

### Verified
- `pytest`: 108 passed (9 new security tests); wasm check + trunk build green.


## 0.13.0 — Quota alerts + admin console (2026-11-17)
### Added
- Quota alerts: per-user threshold from `storage_quotas`, one unread
  `quota_warning` notification generated on real upload/replace usage,
  deduplicated until dismissed; `GET /api/v1/alerts` + dismiss endpoint.
  Server Monitor shows current status and notifications with a dismiss action.
- Admin console API (admins only): system overview, user list with per-user
  usage, user admin-flag updates (self-lockout blocked), and audit feed.
  Embedded in the existing Settings page so the Figma navigation is unchanged.

### Verified
- `pytest`: 99 passed (7 new: 3 alerts + 4 admin); wasm check + trunk build
  green; `/settings` and `/monitor` screenshot-verified dark.


## 0.12.0 — Devices, sync and Android client path (2026-11-17)
### Added
- Devices API: registration (untrusted by default), explicit trust,
  permission grants, heartbeat, revocation, and an Android-facing
  `GET /devices/{id}/backup-config` describing the resumable upload protocol.
- Sync jobs API: queue up/down jobs, completion with checksums, conflict
  detection against the server blob SHA-256, and human resolution
  (accept_server / accept_local).
- Devices page: registration form, trust/revoke controls, backup-config
  viewer, sync-job table and conflict resolution buttons.
- `docs/ANDROID_CLIENT.md`: end-to-end client protocol (no APK shipped;
  explicit about keys not being E2E encryption).

### Verified
- `pytest`: 92 passed (5 new device/sync tests); wasm check + trunk build
  green; `/devices` screenshot-verified dark.


## 0.11.0 — Photo/video library (2026-11-17)
### Added
- Server-side media classification at upload time (magic-byte MIME), with
  PNG/JPEG dimensions and `gps_stripped` metadata; EXIF is never retained.
- `GET /api/v1/media/photos|videos` (album filter), and a thumbnail endpoint
  that generates a local Pillow thumbnail when installed or serves the
  original inline otherwise (no external service).
- Albums API: create/list albums, add/remove files, delete, with live counts.
- Photos/Videos pages: responsive media grid, album filter/creation,
  per-item add-to-album, inline images and Range-streamed `<video>` players.

### Verified
- `pytest`: 87 passed (4 new media tests); wasm check + trunk build green;
  `/photos` screenshot-verified dark.


## 0.10.0 — File version history (2026-11-17)
### Added
- Uploading with `replace_file_id` archives the previous blob as a numbered
  file version (20 per file, oldest pruned); identical content is a no-op.
- `GET /api/v1/files/{id}/versions`, `GET .../versions/{id}/content`,
  `POST .../versions/{id}/restore` (restore is itself versioned).
- Files-page History modal: list versions, download old bytes, restore,
  and upload a replacement from the same screen.

### Verified
- `pytest`: 83 passed (4 new version tests); wasm check + trunk build green.


## 0.9.0 — Backup jobs + Settings page (2026-11-17)
### Added
- Admin-only backup jobs API: `POST/GET/DELETE /api/v1/backups/jobs`,
  `POST .../jobs/{id}/run`, `GET .../jobs/{id}/backups`.
- Backup runs write a self-contained snapshot folder: consistent SQLite
  online snapshot, physical blob copies (optional), and a hashed
  `manifest.json` inventory; runs are verified and old runs pruned by
  retention count.
- Settings page (`/settings`): create/list/run/delete backup jobs, with an
  honest note that cron scheduling is stored but not executed in-process.

### Verified
- `pytest`: 79 passed (4 new backup tests); `trunk build --release` green.

## 0.8.0 — Activity timeline (2026-11-17)
### Added
- `GET /api/v1/activity`: the signed-in user's event feed, paginated.
- Events recorded at real actions only: sign-in/out, upload completion,
  batch delete/restore, share create + downloads, recycle-bin restore and
  permanent delete.
- Activity page (`/activity`): newest-first timeline with kind chips and
  pagination; honest empty state.

### Verified
- `pytest`: 75 passed (4 new activity tests).
- `trunk build --release` green; `/activity` screenshot-verified dark.

## 0.7.0 — Duplicate detection, storage analytics, sharing (2026-11-17)
### Added
- Analytics API: `GET /api/v1/storage/usage` (live usage vs quota, counts)
  and `GET /api/v1/duplicates` (exact copies via shared content blobs,
  wasted bytes per group, biggest waste first).
- Server Monitor page (`/monitor`): server disk, your storage meter,
  duplicate groups with their file lists.
- Sharing (phase 9): `POST/GET /api/v1/shares` + `DELETE .../{id}` (create,
  list, revoke links for files and folders; optional expiry, download
  limit, Argon2id-hashed password) and unauthenticated
  `GET /api/v1/public/shares/{token}[/items|/download|/items/{id}/download]`
  — tokens are stored hashed, links 410 on revoke/expiry/limit, shares die
  with their resource, folder shares only expose that folder's live files.
- Frontend: Share modal in My Files (expiry / limit / password options,
  one-time link copy), Shared Files page (download counts, revoke), and a
  public `/share/{token}` recipient page with password prompt and folder
  listing — works without a session.

### Verified
- `pytest`: 71 passed (16 new: 6 analytics + 10 sharing, incl. password,
  exhaust, expiry, resource-deletion and CSRF cases).
- `cargo check --target wasm32-unknown-unknown` clean;
  `trunk build --release` success; `/monitor`, `/shared`, `/share/{token}`
  screenshot-verified in dark theme.

## 0.6.0 — Recycle bin (2026-11-17)
### Added
- Trash API (`/api/v1/trash`): list top-level deleted items, batch restore,
  permanent delete (`purge`, per-item or whole bin). Files inside a deleted
  folder restore/purge with the folder; listing and storage math count every
  soft-deleted file.
- Purge releases blob refcounts properly: FileVersion/Favorite rows are
  removed first, completed upload records are detached, file rows flushed,
  then blobs that hit zero references are deleted from the database and disk
  (deduplicated blobs stay while any copy survives).
- Recycle Bin page in the Rust frontend (`frontend-rs/src/pages/trash.rs`,
  route `/recycle`): deleted folders + files table (name/type/size/deleted),
  per-row and batch Restore, confirm-gated Delete forever (single, selected,
  or Empty bin), honest empty state, storage-held readout.

### Verified
- `pytest`: 55 passed (8 new recycle-bin tests: listing, cascade restore,
  409 for files inside deleted folders, purge removes row + blob + physical
  bytes, dedup keeps shared blobs, empty bin, CSRF + unknown-id 404).
- `cargo check --target wasm32-unknown-unknown`: clean;
  `trunk build --release`: success.
- `/recycle` screenshot-verified in dark and light themes against the mock
  API at 1920x1080.

## 0.5.0 — Frontend rewrite in Rust (2026-11-16)
### Added
- `frontend-rs/`: the web frontend rewritten in Rust with Yew 0.23 +
  yew-router 0.20, built with Trunk 0.22 — cargo replaces npm/Bun entirely
  (`trunk serve` dev-proxies `/api` to the backend, `trunk build --release`
  produces `frontend-rs/dist/`).
- Full feature parity with the previous React app: session + CSRF auth
  bootstrap, login/first-admin enrollment screen, light/dark theme with
  `prefers-color-scheme` default, resumable chunked uploads with SHA-256
  per chunk (sha2 crate + FileReader slices), file/folder listing with
  sorting, `?folder=` navigation and breadcrumbs, multi-select batch
  move/copy/delete, drag-and-drop (internal re-order + external file drop),
  create/rename modals, folder picker, honest placeholder pages.

### Verified
- `cargo check --target wasm32-unknown-unknown`: 0 errors, 0 warnings.
- `trunk build --release`: success (1.65 MB WASM + 54 KB JS glue).
- All three Figma screens (login 1:70, overview 1:294, my-files 1:636)
  screenshot-verified at 1920x1080 against the mock API in both dark and
  light themes — pixel-faithful to the React implementation; design CSS
  and Figma assets are reused verbatim from `frontend-rs/public/`.

## 0.4.1 — Figma design pass (2026-11-15)
### Added
- The three Figma screens (file `23b5Dvlpat8fRqHtcnfbk2`) implemented in the
  frontend: login `1:70` (`LoginPage.tsx`, `styles/forms.css`), overview
  `1:294` (`OverviewPage.tsx`, `styles/overview.css`), my-files `1:636`
  (`FilesPage.tsx`, `styles/files.css`); new shell `components/Layout.tsx`
  (`styles/layout.css`): top brand bar ("localcloud") + CLOUD/MEDIA/SYSTEM
  tab rows with green active underline + Light/Dark segmented toggle.
- Design tokens in `src/index.css` (dark set from the file, light variant),
  mono uppercase micro-labels, per-page eyebrows/taglines.
- 32 design assets in `src/assets/figma/`: icons normalized to
  `currentColor` so CSS drives active/inactive states, identical photos
  deduped to one `photo-server.png`.
- Designed empty states render only when the real state matches (recent
  uploads empty, folder empty state), per the no-fake-data rule.

### Changed
- Overview storage card now binds to live `/api/health` telemetry with an
  honest "awaiting server data" state only on failure; welcome name from the
  session profile; login "enrollment closed" note from `provider/init`.
- Files sort buttons drive the API `sort`/`order` params; panel footer shows
  `?folder=` breadcrumbs. All Phase 5 behavior (multi-select, DnD, uploads,
  modals) preserved.

### Verified
- `bun --bun run build` clean (313.87 KB JS / 95.11 KB gzip); oxlint: only
  pre-existing benign warnings; backend 47/47 tests pass.
- Login screen screenshot-compared against the Figma node in a scripted
  chromium capture and corrected. Overview/My Files: owner eyeball pass
  pending (authed captures skipped).

## 0.4.0 — Phase 4/5 (2026-11-14)
### Added
- Web UI (React 19 + TypeScript + Vite, runs under Bun): login/first-admin
  enrollment screen with live window detection, responsive light/dark shell,
  session + CSRF token handling (`frontend/src/services/api.ts`).
- Files page wired to the real engine: resumable chunked uploads with
  WebCrypto SHA-256 per chunk and live progress, real listings, ETag-backed
  downloads; Overview page with live disk telemetry from `/api/health`.
- Folder layer (`backend/app/services/folder_service.py`): create/rename/move
  with path maintenance and cycle prevention, recursive soft-delete that
  stamps one `deleted_at` batch (folders + files), cascade-precise restore
  (individually deleted files stay in the bin), stale-path rebuild.
- Folders API (`/api/v1/folders`): children listing, tree, detail with
  breadcrumb, rename, move, delete, restore, batch delete/restore/move.
- Files batch API: move / copy / delete / restore / favorite / unfavorite +
  single-file rename. Copy re-points a new row at the same immutable blob
  (refcount++, upload-style quota check, 413 on exceed).
- Files page folder UX: breadcrumbs, `?folder=` deep links, new-folder and
  rename dialogs, multi-select toolbar, native drag-and-drop (drag items onto
  folders to move, drag OS files onto the page to upload into the open
  folder).

### Verified
- 47/47 backend tests pass (18 new); ruff clean; `npm run build` clean.

## 0.3.0 — Phase 3 (2026-11-10)
### Added
- Content-addressed blob store (`backend/app/storage/blob_store.py`): SHA-256
  keyed files at `storage/files/aa/ab/<hash>.blob`, refcounted `content_blobs`,
  hash-then-rename ordering, disk byte-level identity (`test_blob_layout`).
- Chunked resumable upload API: `POST /uploads` (reserve), `PUT
  .../chunks/{n}` (server-verified per-chunk SHA-256, oversized 413, conflict
  409), `GET /uploads/{id}` (resume state), `POST .../complete` (streaming
  assembly + final hash + dedup + File creation), `DELETE /uploads/{id}`
  (abort + temp purge).
- Local MIME sniffing from magic bytes (stored mime is server-derived), strict
  filename validation at API boundary + defensive sanitizer in service.
- Files API: metadata, content download with ETag/`If-None-Match` 304,
  single-range & suffix Range streaming (206/416 per RFC 9110).
- Quota + disk guardrails: per-user default quota; uploads refused with 507
  when disk reaches 85% or below the 30 GB reserve (never auto-delete).
- pytest storage suite: chunk mismatch, staging-cap, idempotent resume,
  missing-chunks completion guard, abort cleanup, dedup refcount assertions,
  quota + guardrail env-driven tests, IDOR ownership guard.

### Verified
- 29/29 tests pass; ruff clean (B008 FastAPI idiom ignored).

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

