# MyCloud — Security architecture

Status: design committed at Phase 1. Implementation verified phase-by-phase;
**no security claim is final until the Phase 15 test suite passes.**

## Controls committed to design

| Threat | Control |
|---|---|
| SQL injection | SQLAlchemy 2.0 parameterized ORM/queries only; no string-built SQL |
| XSS | React auto-escaping; no `dangerouslySetInnerHTML`; strict `Content-Security-Policy` served by reverse proxy; user files served as `application/octet-stream` + `Content-Disposition: attachment` unless whitelisted-safe mime |
| CSRF | DB session carries its own CSRF token; double-submit header `X-CSRF-Token`; cookie `SameSite=Strict`; origin check on mutations |
| Session theft | HttpOnly + Secure (prod) + SameSite=Strict cookies; rotating token hash stored, not the token; idle + absolute expiries; revocation list consulted every request |
| Brute force | Login rate limiter (per-IP + per-account), exponential backoff, lockout with audit events |
| Path traversal | Storage layer uses only DB-issued IDs + SHA-256 hex paths; user-provided names never concatenated into filesystem paths; `realpath` containment checks with negative tests |
| IDOR / broken access control | Every repository call takes `owner_id` from the authenticated session, never from the client |
| Malicious uploads | MIME sniffed server-side; files stored outside web root; never executed; archive handling excluded in v1; size limits enforced pre- and per-chunk |
| Unsafe previews | Thumbnails generated locally, re-encoded to JPEG/PNG derivatives — originals never served as preview markup |
| Resource exhaustion | Streaming (chunked) I/O, per-user quota, global disk guardrails (85% floor, 30 GB reserve), upload temp expiry GC, pagination caps |
| EXIF privacy | GPS and thumbnail EXIF tags stripped on ingest and on share-link downloads; stripping recorded in media_metadata |
| Secrets | Argon2id hashes; opaque session tokens (hashed at rest); no password/token ever logged; `.env` never committed |

## Binding rules
- Development: uvicorn on `127.0.0.1` only. Never expose the dev server.
- SSH currently listens on `0.0.0.0` (system finding). Recommendation recorded in
  DEPLOYMENT.md: bind SSH to LAN/Tailscale interface or firewall it — **requires
  user-approved privileged change, not performed unilaterally**.
- Admin endpoints re-check `is_admin` server-side on every request; the UI hides
  admin pages but that is only cosmetic.

## Secure initial administrator (no default credentials)
1. If `users` table has zero admins, `/auth/provider/init` opens a one-time
   enrollment window stamped in a protected file (mode 0600) on the server.
2. The window closes after creating the first admin or after expiry.
3. If the service has ever had an admin, init endpoints are permanently 403.

## Verification plan (Phase 15)
pytest suite covering: IDOR matrix (user A cannot touch B's resources), traversal
attempts (`../`, encoded, absolute), CSRF enforcement, session fixation/rotation,
rate-limit behavior, upload chunk corruption detection, share expiry/limit/password,
path containment fuzzing, header/CSP presence, quarantine handling of spoofed MIME.
