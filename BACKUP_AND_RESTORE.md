# MyCloud — Backup and disaster recovery

## Principles
- A backup on the same physical disk is NOT disaster protection (spec §20). The
  platform records `destination` on every `backups` row; alerts distinguish
  same-disk copies from external destinations.
- Never overwrite a valid backup in place: new backup is written fully, verified
  (SHA-256 of manifest + content), **then** the oldest backup beyond retention is
  removed, in that order.

## What is backed up
| Object | Method |
|---|---|
| SQLite DB | `sqlite3 .backup` API into a versioned file (hot, transaction-consistent); future PostgreSQL: `pg_dump` equivalent through the same job interface |
| Configuration | `.env` (secrets kept file-mode 0600; restore operator must know .env policy), deployment units, proxy config |
| Metadata | Alembic migration state + `alembic heads` snapshot recorded in manifest |
| User files | Mode A: copy verified `content_blobs` (default). Mode B: manifest-only (blobs stay in place; external restore requires the original storage tree — documented limitation) |

## Job pipeline (Phase 14)
1. `backup_jobs` define name, schedule, retention count, blob mode, destination
   (`backups/` by default; external path/rsync target configurable — free/local only).
2. Runner freezes a manifest (DB row snapshot list, blob hash list), copies
   incrementally to `backups/<job>/<ts>/`, hashes manifest, writes
   `manifest.sha256`, verifies full content hash, marks state verified/failed.
3. Restore: verify manifest first, restore DB to staging path, run Alembic upgrade
   check (forward-only note in db is version-pinned), swap paths with operator
   confirmation, restart service. Restore IS an irreversible operation — always
   gated behind explicit admin action.
4. History + verification sweep retained; failure sends notification event.

## Operator runbook (manual, no platform involved)
1. Stop writes (systemd stop mycloud-backend) — or rely on `.backup` API lock.
2. `cp database/mycloud.db*` AND `cp -a storage/` to external medium.
3. Verify with `sha256sum -c manifest.sha256`.
4. Recovery steps mirrored in the admin UI restore action.
