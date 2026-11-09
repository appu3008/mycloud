# MyCloud — Database design

Engine: SQLite 3.53 (WAL mode) via SQLAlchemy 2.0. Migrations: Alembic.
Portability: only `MYCLOUD_DATABASE_URL` is provider-specific; switching to
PostgreSQL later requires one URL change and an Alembic migration — no model rewrites.
SQLite pragmas set at engine creation: `journal_mode=WAL`,
`foreign_keys=ON`, `synchronous=NORMAL`.

Conventions: UTC timestamps (`datetime, db_utcnow()`), UUIDv4 string PKs for
external-facing entities, real `UNIQUE`/`CHECK`/`FK` constraints, `ON DELETE` rules
protecting blobs (soft-delete friendly). Migrations live in `backend/migrations/`.

## Entities (20)

### users
`id` TEXT PK · `email` TEXT UNIQUE NOT NULL · `password_hash` TEXT NOT NULL
(Argon2id) · `display_name` TEXT NOT NULL · `role` TEXT CHECK(admin|user) NOT NULL
DEFAULT 'user' · `is_active` BOOL DEFAULT 1 · `is_admin` BOOL DEFAULT 0
· `password_changed_at` · `created_at` · `updated_at` · `last_login_at`
Index: `ix_users_email`.

### sessions
`id` TEXT PK (opaque token hash, raw token never stored) · `user_id` FK->users
ON DELETE CASCADE · `device_id` FK->devices NULL · `ip_address` TEXT NULL ·
`user_agent` TEXT NULL · `csrf_token` TEXT NOT NULL · `created_at` ·
`last_seen_at` · `expires_at` · `abs_expires_at` · `revoked_at` NULL
Index: `ix_sessions_user`, `ix_sessions_expires`.

### devices
`id` TEXT PK · `user_id` FK->users ON DELETE CASCADE · `name` TEXT ·
`platform` TEXT · `public_key` TEXT NULL (future E2E) · `trust_level`
CHECK(untrusted|trusted) · `can_sync` BOOL · `can_backup` BOOL ·
`last_seen_at` · `created_at` · `revoked_at` NULL
Unique: (`user_id`, `name`).

### folders
`id` TEXT PK · `owner_id` FK->users ON DELETE CASCADE · `parent_id` FK->folders
NULL (tree) · `name` TEXT · `path` TEXT (normalized display path, unique per owner) ·
`created_at` · `updated_at` · `deleted_at` NULL (soft delete)
Unique: (`owner_id`, `parent_id`, `name`) · Index: `ix_folders_owner`,
`ix_folders_parent`, `ix_folders_deleted`.

### files
`id` TEXT PK · `owner_id` FK->users ON DELETE CASCADE · `folder_id` FK->folders NULL ·
`name` TEXT · `extension` TEXT · `mime_type` TEXT · `size_bytes` INT ·
`sha512_hint` TEXT NULL (short, for quick scan) · `blob_id` FK->content_blobs ·
`mtime` · `created_at` · `updated_at` · `deleted_at` NULL · `is_favorite` BOOL ·
`fts_rowid` INT NULL (link to FTS table)
Index: owner, folder, mime, deleted, `ix_files_name_fts` via FTS5 virtual table
`files_fts(name, extension)`.

### content_blobs
`sha256` TEXT PK (hex) · `size_bytes` INT · `ref_count` INT NOT NULL (files +
versions + uploads pinned) · `encrypted_size_bytes` INT NULL · `storage_path` TEXT ·
`created_at` · `last_verified_at` NULL (integrity check sweep)
Rule: delete physical file only when `ref_count` reaches 0, inside a transaction.

### file_versions
`id` TEXT PK · `file_id` FK->files ON DELETE CASCADE · `version_number` INT ·
`blob_id` FK->content_blobs · `size_bytes` · `created_by` (action: rename/move/
replace/sync/restore) · `created_at` Unique: (`file_id`,`version_number`).

### uploads / upload_chunks
`uploads`: `id` PK · `user_id` FK · `target_folder_id` FK NULL ·
`filename` · `size_bytes` · `chunk_size_bytes` · `total_chunks` ·
`received_chunks` INT · `state` CHECK(reserved|uploading|assembling|complete|
failed|aborted) · `final_blob_id` FK NULL · `created_at` · `updated_at` ·
`expires_at` (temp GC) · `client_upload_id` TEXT (resumability key).
`upload_chunks`: `upload_id` FK · `chunk_number` · `sha256` · `size_bytes` ·
`storage_path` (temp dir) · `saved_at` Unique: (`upload_id`,`chunk_number`).

### shares
`id` TEXT PK · `resource_type` CHECK(file|folder) · `file_id` FK NULL ·
`folder_id` FK NULL · `owner_id` FK->users · `token_hash` TEXT UNIQUE (SHA-256 of
random 32-byte token) · `mode` CHECK(download|readonly|upload) ·
`password_hash` TEXT NULL (Argon2id) · `max_downloads` INT NULL ·
`download_count` INT · `expires_at` NULL · `created_at` · `revoked_at` NULL.
Index: `owner_id`, `resource`.

### albums / album_files
`albums`: `id` PK · `owner_id` FK · `name` Unique(owner,name) · `description` ·
`cover_file_id` FK->files NULL · `created_at`. `album_files`: album FK · file FK ·
added_at Unique: (`album_id`,`file_id`).

### media_metadata
`file_id` FK->files ON DELETE CASCADE PK · `kind` CHECK(photo|video) ·
`width` · `height` · `duration_seconds` · `captured_at` (EXIF) · `exif_json` TEXT
(gps stripped by default; `gps_stripped` BOOL) · `thumbnail_path` ·
`created_at` Index: `captured_at`, `kind`.

### backups / backup_jobs
`backup_jobs`: `id` PK · `name` · `target_path` · `include_content_blobs` BOOL ·
`schedule_cron` TEXT NULL · `retention_count` INT · `enabled` BOOL · `created_at`.
`backups`: `id` PK · `job_id` FK->backup_jobs · `manifest_sha256` ·
`content_sha256` · `size_bytes` · `state` CHECK(running|verified|failed) ·
`started_at` · `finished_at` · `restored_at` NULL · `destination` TEXT.

### sync_jobs
`id` PK · `device_id` FK->devices · `file_id` FK->files · `direction`
CHECK(up|down) · `state` CHECK(queued|running|done|conflict|failed) ·
`local_checksum` · `server_checksum` · `conflict_strategy`
CHECK(newer_wins|conflict_copy) · `error` TEXT NULL · `attempts` INT ·
`created_at` · `updated_at`.

### favorites
`user_id` FK · `file_id` FK · `created_at` Unique: (`user_id`,`file_id`).

### notifications
`id` PK · `user_id` FK · `type` TEXT · `payload_json` TEXT · `is_read` BOOL ·
`created_at` Index: (`user_id`,`is_read`).

### storage_quotas
`user_id` PK FK->users · `quota_bytes` INT · `notify_threshold_pct` INT DEFAULT 85 ·
`updated_at`.

### audit_logs
`id` INTEGER PK AUTOINCREMENT · `actor_user_id` FK NULL (system events) ·
`actor_email` TEXT NULL (indexed; lockout lookup key) · `actor_ip` TEXT NULL
(indexed; per-IP spray guard) · `action` TEXT (`auth.login.failed`,
`auth.login.locked`, …) · `target_type`/`target_id` NULL · `detail` TEXT
(never secrets/passwords/tokens) · `created_at` Index: (`created_at`),
(`actor_user_id`), (`actor_email`), (`actor_ip`), (`action`). Append-only;
deletion only by retention job. Login lockout counts query this table
(durable, multi-worker safe): 5 account failures / 15 min => 15 min lockout;
per-IP spray cap at 4x the account threshold.

### op request context
Relative `MYCLOUD_STORAGE_ROOT`, `MYCLOUD_DATA_DIR`, and sqlite `DATABASE_URL`
values are resolved against the project root at settings validation time, so
behavior never depends on the process CWD.

### activity_events
`id` PK · `user_id` FK (visibility owner) · `kind` CHECK(upload|download|delete|
restore|share|login|logout|device|backup|folder|admin) · `file_id` FK NULL ·
`summary` TEXT · `created_at` Index: (`user_id`,`created_at` DESC).
