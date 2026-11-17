# Android backup client path

MyCloud does not ship a native APK in this repository. Instead, the server
exposes a documented, testable protocol that an Android client (native Kotlin
or a WebView wrapper) can implement against a self-hosted instance. The
protocol uses only endpoints that already exist in the backend.

## 1. Sign in and register the device

1. `POST /api/v1/auth/login` with `{"email", "password"}`; keep the session
   cookie and the returned `csrf_token`.
2. Send the cookie on every request; send `X-CSRF-Token: <csrf_token>` on every
   mutating request (`POST`, `PATCH`, `DELETE`).
3. `POST /api/v1/devices` with
   `{"name": "Pixel 8", "platform": "android", "public_key": "<optional>"}`.
   The device starts **untrusted** and cannot sync or back up.
4. Ask the owner to open **Devices** in the web UI and press **Trust**. Trust
   grants `can_sync` and `can_backup` explicitly; **Revoke** immediately
   disables both.

A registration response includes the device `id`; store it locally.

## 2. Discover the backup protocol

`GET /api/v1/devices/{id}/backup-config` returns the authoritative endpoints
(read-only, no CSRF needed):

```json
{
  "upload_endpoint": "/api/v1/uploads",
  "chunk_endpoint": "/api/v1/uploads/{upload_id}/chunks/{number}",
  "complete_endpoint": "/api/v1/uploads/{upload_id}/complete",
  "auth": "session cookie + X-CSRF-Token header",
  "chunk_checksum_header": "X-Chunk-Sha256",
  "max_chunk_mb": 16
}
```

The endpoint returns `403` until the device is trusted and allowed to back up,
and `410` once revoked. The web UI also displays this config via the
**Backup config** button, so a user can verify what a client is told.

## 3. Back up a file (chunked, resumable)

For each photo/video/local document:

1. `POST /api/v1/uploads` with
   `{"filename", "size_bytes", "target_folder_id": null, "chunk_size_mb": 4}`.
   Save `upload_id`, `chunk_size`, and `total_chunks`.
2. For each chunk `n` (1-based):
   `PUT /api/v1/uploads/{upload_id}/chunks/{n}` with the raw bytes and
   `X-Chunk-Sha256: <hex SHA-256 of this chunk>`. Re-sending the same chunk is
   idempotent, so an interrupted backup resumes at the last acknowledged chunk.
3. `POST /api/v1/uploads/{upload_id}/complete` with `{}` (or
   `{"replace_file_id": "..."}` to keep version history when updating a file).

Storage is content-addressed: uploading identical bytes twice creates a second
file row but reuses the same physical blob. Quota and free-disk checks are
enforced server-side at reservation and completion.

## 4. Sync jobs and conflicts

- `POST /api/v1/sync/jobs` with
  `{"device_id", "file_id", "direction": "up"|"down", "local_checksum"}` queues
  work. A `down` job whose local checksum differs from the server blob is
  created in `conflict` state.
- `GET /api/v1/sync/jobs?device_id={id}` lists jobs and their states.
- `POST /api/v1/sync/jobs/{job_id}/complete` with
  `{"checksum": "<sha256>"}` finishes a queued job.
- Conflicts require a human decision in the web UI: **Keep server**
  (`accept_server`) or **Keep device** (`accept_local`) via
  `POST /api/v1/sync/jobs/{job_id}/resolve`.
- `POST /api/v1/devices/{id}/heartbeat` refreshes `last_seen_at` so the owner
  can see the device is alive.

All mutating calls require the CSRF header and an active, trusted, non-revoked
device. Activity events are recorded in `/api/v1/activity` for transparency.

## 5. Scope and privacy

- No telemetry, third-party relay, or cloud account: the client talks directly
  to the owner's server URL.
- EXIF/GPS is never parsed or stored by the media subsystem; photos are
  classified by server-side MIME sniffing only.
- The optional `public_key` field is reserved for future device-bound keys;
  today authentication is via the user's session cookie. Do not treat it as
  end-to-end encryption.
