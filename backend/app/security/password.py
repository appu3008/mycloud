"""Argon2id password hashing.

argon2-cffi defaults match OWASP Password Storage guidance for Argon2id
(time_cost=3, memory_cost=65536, parallelism=4). Hashes are verified with
constant-time comparison inside the library.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(plain: str) -> str:
    """Hash with a fresh random salt; output is an encoded PHC string."""
    return _hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain)
    except VerifyMismatchError:
        return False
    except (VerificationError, ValueError):
        # Malformed/unverifiable hash -> treat as failure (never crash auth).
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when parameters have been upgraded; drives transparent rehash."""
    return _hasher.check_needs_rehash(password_hash)
