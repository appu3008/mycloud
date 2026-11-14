# Roadmap / task tracker

Completed tasks are checked with the phase that verified them. No phase is
"complete" until its tests run and pass.

## Phase 1 — foundation (done)
- [x] Environment inspection (docs/ENVIRONMENT.md)
- [x] Directory scaffold + module packages
- [x] Settings via env (no hardcoded secrets)
- [x] FastAPI skeleton + /api/health (real checks)
- [x] Docs set (architecture, DB schema, API, security, deployment, backup)
- [x] .gitignore, .env.example, requirements.txt, systemd example, compose (inert)

## Phase 2 — database & auth
- [x] SQLAlchemy models (20 entities + album_files) + engine/session factory (WAL, FK on)
- [x] Alembic init + initial migration (applied to dev database: 22 tables)
- [x] Argon2id hashing (argon2-cffi, OWASP-aligned params, transparent rehash)
- [x] First-admin bootstrap window (enrollment marker file, closed after use)
- [x] DB-backed sessions (hashed tokens, CSRF via X-CSRF-Token, idle+absolute expiry)
- [x] Login rate limiting + lockout (audit-driven, durable across workers/restarts)
- [x] Session revocation (own sessions + all-others on password change)
- [x] Registration endpoint closed (invite tokens arrive Phase 12) — honest 403
- [x] pytest (10 tests): enrollment, uniform login errors, CSRF, lockout,
      logout, password-change revocation, session revoke, history, health

## Phase 3 — storage engine
- [ ] Blob store (sha256 content addressing, refcounts, crash-safe ordering)
- [ ] Chunked resumable uploads + per-chunk + final checksums + temp GC
- [ ] Quota enforcement + disk guardrails
- [ ] pytest: chunk corruption, resume, dedup, quota, traversal

## Phase 3 — storage engine (done)
- [x] Content-addressed blob store (sha256 addressing, refcounts, crash-safe
      put-temp-then-rename, dedup safe across users)
- [x] Chunked resumable uploads: reserve/chunk/complete/abort/state API,
      per-chunk SHA-256 (server-verified, idempotent re-PUT), stream-assembly
      (RAM-bounded staging), final hash integrity
- [x] Quota enforcement (default per-user on settings, admin per-user rows later)
- [x] Disk guardrails: 85% cap + minimum reserve; uploads get 507, never delete
- [x] Filename MIME sniffing (local magic bytes) + traversal-proof naming
- [x] Files API: metadata, listing, Range/ETag streaming download (RFC 9110)
- [x] pytest (19 new incl. IDOR guard, dedup refcounts, temp cleanup, range 416s)

## Phase 4 — file manager frontend
- [ ] Vite/React/TS scaffold, theming, responsive shell
- [ ] Files/folders pages wired to real API (upload/download/move/copy/delete/sort/search/multiselect/DnD)
- [ ] Vitest + integration via backend test server

## Phase 5 — folders & batch operations (done)
- [x] Folder service: create/rename/move with live path maintenance, cycle
      prevention, unique-name conflicts (409), ownership scoping everywhere
- [x] Recursive soft-delete cascades (folders + files share one deleted_at
      batch); restore returns exactly that batch — individually-deleted files
      stay in the bin; stale paths rebuilt on restore
- [x] Folders API: list children, tree, detail+breadcrumb, rename, move,
      delete, restore, folder batch (delete/restore/move)
- [x] Files API: batch move/copy/delete/restore/favorite + single rename;
      copy re-points rows at the same blob (refcount++, quota-checked)
- [x] Files page: breadcrumb navigation, create/rename dialogs, multi-select
      with toolbar, HTML5 drag-and-drop (items between folders, OS files in),
      uploads target the open folder
- [x] pytest (18 new: 47 total) — naming/traversal, conflicts, cycles,
      cascade restore semantics, IDOR + CSRF on every folder route

## Phases 5–17
- [ ] Media (photos/videos/albums/thumbnails/streaming/EXIF GPS stripping)
- [ ] Recycle bin + version history (retention policies)
- [ ] Duplicate detection + savings report
- [ ] Sharing (tokens, passwords, expiry, limits, revoke)
- [ ] Devices + sync (conflict-copy, queues, revocation)
- [ ] Android backup client path (real background caveat documented)
- [ ] Storage analytics + server monitoring (hwmon, sensors)
- [ ] Admin console + audit/activity trails
- [ ] Optional E2E encryption design gate
- [ ] Backup/restore jobs + external destinations
- [ ] Security suite (IDOR/traversal/CSRF/rate-limit matrix)
- [ ] Tailscale connectivity + HTTPS strategy
- [ ] Production hardening (systemd, proxy, compose once Docker available)
