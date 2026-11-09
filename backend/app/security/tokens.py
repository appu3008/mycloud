"""Cryptographically secure token generation and hashing.

Session cookie tokens: 32 random bytes -> urlsafe base64 (43 chars).
Only SHA-256 hashes of tokens are persisted, so a database leak does not
yield usable session cookies. Share tokens use the same source but store
sha256 hex for lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_TOKEN_BYTES = 32


def new_session_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def new_share_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Stable SHA-256 hex of a token (used as sessions PK / share lookup)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
