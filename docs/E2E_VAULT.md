# End-to-end encrypted vault (optional)

The vault is **client-side only**: the browser encrypts a file before upload
and decrypts it after download. The server stores opaque bytes and never sees
the passphrase or plaintext. It is available in **Settings -> End-to-end
encrypted vault**.

## How it works

1. You choose a passphrase (at least 8 characters) and a local file.
2. The browser generates a fresh 16-byte salt and 12-byte IV with
   `crypto.getRandomValues`.
3. PBKDF2-SHA-256 with 250 000 iterations derives a 256-bit AES-GCM key from
   the passphrase and salt.
4. The plaintext is encrypted with AES-256-GCM (128-bit tag).
5. The uploaded `.vault` file is:
   `b"MYCE1" | salt[16] | iv[12] | ciphertext+tag`.
6. Decryption reverses the process entirely in the browser and offers the
   plaintext as a download through an object URL.

Uploads use the same resumable `/api/v1/uploads` endpoints as ordinary files,
so quota, deduplication, range downloads and backups all keep working — the
server simply handles ciphertext.

## What this does and does not protect

- **Protects**: server/database operators, backups, and anyone who obtains the
  stored file or token cannot read the contents without the passphrase.
- **Does not protect**: a compromised browser, keylogger, or malicious
  JavaScript served by the same origin. Metadata (filename, size, upload
  time) is visible because the API needs it.
- **No key recovery**: losing the passphrase makes the data unrecoverable.
  This is by design; there is no escrow or reset path.
- This is independent of the device `public_key` field, which is reserved for
  future device-bound authentication and is **not** end-to-end encryption.

The implementation lives in `frontend-rs/src/e2e.rs` and uses only standard
WebCrypto primitives available on HTTPS/localhost.
