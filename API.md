# MyCloud — REST API design (v1)

Base URL: `/api/v1`. Auth: `mycloud_session` HttpOnly cookie + `X-CSRF-Token`
header on all mutating requests. Errors: `{"detail": {...}}`, standard codes.

## Conventions
- Pagination: `?page=&page_size=` (default 50, max 200), responses include total.
- Sorting: `?sort=name|size|mtime|uploaded&order=asc|desc`.
- Search: `GET /api/v1/search?q=` (+ filters below).
- Streaming downloads support `Range` (`Accept-Ranges: bytes`).
- Mutating endpoints require CSRF header; session cookie is SameSite=Strict.

## Auth — `security/`
| Verb/path | Purpose |
|---|---|
| POST `/auth/provider/init` | Create first admin ONLY if zero admin exists (proof-of-possession challenge, never default creds) |
| POST `/auth/register` | Admin-invited registration (Phase 2: invite tokens) |
| POST `/auth/login` | Email+password -> session; rate-limited + lockout |
| POST `/auth/logout` | Revoke current session |
| GET `/auth/me` | Profile |
| PATCH `/auth/me` | Display name / prefs |
| PATCH `/auth/me/password` | Change password (rehash, invalidate other sessions) |
| GET `/auth/sessions` · DELETE `/auth/sessions/{id}` | Device sessions + revocation |
| GET `/auth/login-history` | Own login history |

## Uploads — `api/uploads.py` (resumable, chunked)
| Verb/path | Purpose |
|---|---|
| POST `/uploads` | Reserve upload: returns `{id, chunk_size, received, exists_sha256?}` |
| GET `/uploads/{id}` | Resume state (per chunk bitmap) |
| PUT `/uploads/{id}/chunks/{n}` | Body bytes; `X-Chunk-Sha256` verified, idempotent per chunk |
| POST `/uploads/{id}/complete` | Assemble -> final SHA-256 -> dedup -> file row |
| DELETE `/uploads/{id}` | Abort + cleanup temp |
| GET `/uploads?state=active` | Active uploads (storage section 15) |

## Files & folders — `api/files.py`
| Verb/path | Purpose |
|---|---|
| GET `/files` | List (folder view: `?folder_id=`, root default) |
| POST `/files` | Save completed upload to folder (used by complete) |
| GET `/files/{id}` | Metadata |
| GET `/files/{id}/content` | Download (Range, ETag=sha256) |
| PATCH `/files/{id}` | Rename/move/copy targets |
| POST `/files/{id}:copy` · POST `/files/{id}:move` | `body{target_folder_id}` |
| DELETE `/files/{id}` | Soft delete -> recycle |
| POST `/files/batch` | Multi-select ops: `{op: move|copy|delete|restore|favorite|unfavorite, ids[]}` |
| GET/PUT `/files/{id}/favorite` | favorites |
| GET `/files/{id}/versions` · POST `/files/{id}/versions/{n}:restore` · DELETE `/files/{id}/versions/{n}` | Version history (section 6) |
| POST `/files/{id}/duplicate-check` | SHA-256 comparison report (section 8) |

## Folders
POST `/folders` · GET `/folders/{id}` · PATCH `/folders/{id}` ·
POST `/folders/{id}:move` · DELETE `/folders/{id}` (recursive soft delete) ·
GET `/folders/{id}/tree` (lazy children)

## Recycle bin — `api/recycle.py`
GET `/recycle` | POST `/recycle/{entry_id}:restore` | DELETE `/recycle/{entry_id}`
(permanent, explicit) | POST `/recycle:empty` (explicit) | GET `/recycle:size`

## Media — `api/media.py`
GET `/media/photos` · GET `/media/videos` (date-grouped, `?group=month`) ·
GET `/files/{id}/thumbnail` (re-encoded derivative) · GET `/files/{id}/stream`
(video Range streaming) · Albums CRUD: `/albums`, `/albums/{id}/files`,
`POST /albums/{id}/files/{file_id}`

## Shares — `api/shares.py`
POST `/shares` (`{resource_id, mode, password?, expires_at?, max_downloads?}`) ·
GET `/shares` (own) · DELETE `/shares/{id}` (revoke) · GET
`/shares/{id}/activity` · Public: POST `/s/{token}/unlock` (password), GET
`/s/{token}/download`, POST `/s/{token}/upload` (upload-only mode)

## Devices & sync — `api/devices.py`, `api/sync.py`
POST `/devices/register` · GET `/devices` · PATCH `/devices/{id}` (permissions) ·
DELETE `/devices/{id}` (revoke + sessions) · GET `/sync/poll?since=` (changes) ·
POST `/sync/upload` · GET `/sync/push-state` · POST `/sync/resolve`
(`{job_id, strategy: conflict_copy|accept_server|accept_local}`) — conflict-copy
NEVER overwrites (section 11).

## Storage & monitoring — `api/storage.py`, `api/monitor.py`
GET `/storage/usage` (capacity, free, per-type breakdown, largest files, bin,
temp) · GET `/storage/alerts` · GET `/monitor/summary` (CPU/RAM/disk/net/temp/
sessions/uploads/downloads) — admin-only for system-level detail; user-level is
scoped to own activity.

## Admin — `api/admin.py` (server-side `is_admin` checks)
GET/POST/PATCH/DELETE `/admin/users…` (create, disable, quota, role) ·
POST `/admin/users/{id}:revoke-sessions` · GET `/admin/shares` · GET
`/admin/audit-logs?filter…` · GET `/admin/login-history` · GET
`/admin/failed-logins` · POST `/admin/backups/run/{job_id}` · GET `/admin/backups` ·
GET `/admin/system-health`

## Activity & notifications
GET `/activity?kind=&page=` · GET `/notifications` · POST `/notifications:read-all`

## Settings (server config surfaced)
GET `/settings` · PATCH `/settings` (admin: upload caps, retention, theme defaults)
