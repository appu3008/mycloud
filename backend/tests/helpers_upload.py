"""Test helpers shared by storage-engine tests."""

from __future__ import annotations

import hashlib


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def chunks_for(data: bytes, size: int) -> list[bytes]:
    if size <= 0 or not data:
        return [data] if data else []
    chunks = [data[i : i + size] for i in range(0, len(data), size)]
    # last chunk must match upload chunk size rules (accept any length)
    return chunks
