"""Phase 3 edge tests: quota, guardrails, ranges, blob layout."""

from __future__ import annotations

import os

from tests.helpers_upload import sha256_hex
from tests.test_uploads import _init_upload, _upload_file


def test_quota_exceeded_rejected(client, admin_auth):
    os.environ["MYCLOUD_DEFAULT_QUOTA_MB"] = "1"
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        first = _upload_file(client, admin_auth, os.urandom(700 * 1024), filename="q1.bin")
        assert first["size_bytes"] == 700 * 1024

        init = _init_upload(client, size=700 * 1024, csrf=admin_auth["csrf_token"])
        assert init.status_code == 413
        assert init.json()["detail"]["error"] == "quota_exceeded"
    finally:
        os.environ.pop("MYCLOUD_DEFAULT_QUOTA_MB", None)
        get_settings.cache_clear()


def test_disk_guardrail_refuses_writes(client, admin_auth):
    os.environ["MYCLOUD_MIN_FREE_SPACE_MB"] = "999999999"
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        init = _init_upload(client, size=1024, csrf=admin_auth["csrf_token"])
        assert init.status_code == 507
        assert init.json()["detail"]["error"] == "disk_protected"
    finally:
        os.environ.pop("MYCLOUD_MIN_FREE_SPACE_MB", None)
        get_settings.cache_clear()


def test_lighthttp_range_single_partial(client, admin_auth):
    payload = os.urandom(2048)
    info = _upload_file(client, admin_auth, payload, filename="range.bin")

    partial = client.get(
        f"/api/v1/files/{info['id']}/content", headers={"Range": "bytes=100-219"}
    )
    assert partial.status_code == 206
    assert partial.content == payload[100:220]
    assert partial.headers["content-range"] == f"bytes 100-219/{len(payload)}"
    assert int(partial.headers["content-length"]) == 120


def test_range_suffix_and_open_end(client, admin_auth):
    payload = os.urandom(2048)
    info = _upload_file(client, admin_auth, payload, filename="range2.bin")

    suffix = client.get(
        f"/api/v1/files/{info['id']}/content", headers={"Range": "bytes=-64"}
    )
    assert suffix.status_code == 206
    assert suffix.content == payload[-64:]

    tail = client.get(
        f"/api/v1/files/{info['id']}/content", headers={"Range": "bytes=2000-"}
    )
    assert tail.status_code == 206
    assert tail.content == payload[2000:]


def test_range_invalid_rejected(client, admin_auth):
    payload = os.urandom(1024)
    info = _upload_file(client, admin_auth, payload, filename="range3.bin")
    multi = client.get(
        f"/api/v1/files/{info['id']}/content", headers={"Range": "bytes=0-100,200-300"}
    )
    assert multi.status_code == 416
    out_of_bounds = client.get(
        f"/api/v1/files/{info['id']}/content", headers={"Range": "bytes=99999-"}
    )
    assert out_of_bounds.status_code == 416


def test_etag_304_roundskip(client, admin_auth):
    payload = os.urandom(512)
    info = _upload_file(client, admin_auth, payload, filename="etag.bin")
    etag = client.get(f"/api/v1/files/{info['id']}/content").headers["etag"]
    conditional = client.get(
        f"/api/v1/files/{info['id']}/content", headers={"If-None-Match": etag}
    )
    assert conditional.status_code == 304


def test_blob_layout_matches_architecture_hash_positions(client, admin_auth):
    """Physical bytes must live at files/aa/ab/<sha256>.blob (ARCHITECTURE.md)."""
    from app.core.config import get_settings
    from app.storage import blob_store

    payload = os.urandom(321)
    _upload_file(client, admin_auth, payload, filename="layout.bin")
    digest = sha256_hex(payload)
    path = get_settings().files_dir / blob_store.blob_relpath(digest)
    assert path.is_file()
    assert path.read_bytes() == payload
    assert blob_store.blob_exists(get_settings(), digest)


def test_operations_cannot_touch_other_users_files(client, admin_auth):
    """IDOR guard: uploads and reads are per-owner only."""
    from fastapi.testclient import TestClient

    payload = os.urandom(256)
    info = _upload_file(client, admin_auth, payload, filename="mine.bin")
    intruder = TestClient(client.app)
    # no login at all -> 401 everywhere
    assert intruder.get(f"/api/v1/files/{info['id']}").status_code == 401
    assert intruder.get(f"/api/v1/files/{info['id']}/content").status_code == 401
