"""Local MIME sniffing (magic bytes) + filename sanitization.

Client-supplied MIME strings are treated as untrusted hints; the stored value
comes from server-side sniffing of the first bytes, falling back to
application/octet-stream. Filenames are normalized and de-pathed so they are
safe display strings only — the storage layer never uses them for paths.
"""

from __future__ import annotations

import unicodedata

OCTET_STREAM = "application/octet-stream"


def sanitize_filename(name: str, max_length: int = 240) -> str:
    normalized = unicodedata.normalize("NFC", name).strip()
    # Remove control characters and path separators.
    cleaned = "".join(
        ch for ch in normalized if ch.isprintable() and ch not in "/\\"
    )
    cleaned = cleaned.lstrip(".")  # no dotfiles / masking names
    if not cleaned:
        return "unnamed"
    if ".." in cleaned:
        cleaned = cleaned.replace("..", "_")
    return cleaned[:max_length]


def extension_of(name: str) -> str:
    _, ext = __import__("os").path.splitext(name)
    return ext.lower().lstrip(".")[:16]


_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"OggS", "application/ogg"),
    (b"fLaC", "audio/flac"),
    (b"ID3", "audio/mpeg"),
    (b"RIFF", "application/octet-stream"),  # RIFF containers resolved below
    (b"\x1f\x8b", "application/gzip"),
    (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
    (b"BZh", "application/x-bzip2"),
    (b"\x00\x61\x73\x6d", "application/wasm"),
    (b"{\\rtf", "application/rtf"),
)


def sniff_mime(head: bytes) -> str:
    """Best-effort local detection from the first bytes (never external)."""
    if not head:
        return OCTET_STREAM
    for magic, mime in _MAGIC:
        if head.startswith(magic):
            if magic == b"RIFF":
                if len(head) >= 12 and head[8:12] == b"WEBP":
                    return "image/webp"
                if len(head) >= 12 and head[8:12] == b"WAVE":
                    return "audio/wav"
                if len(head) >= 12 and head[8:12] == b"AVI ":
                    return "video/x-msvideo"
                return OCTET_STREAM
            if magic == b"PK\x03\x04" and b"word/" in head[:64]:
                return (
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                )
            if magic == b"PK\x03\x04" and b"xl/" in head[:64]:
                return (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            return mime
    if head[:4].rstrip(b"\x00") == b"ftyp" or (len(head) >= 12 and head[4:8] == b"ftyp"):
        return "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):  # EBML = Matroska/WebM
        return "video/webm"
    return OCTET_STREAM
