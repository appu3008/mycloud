"""Media library tests: classification, metadata, thumbnails, albums."""

from __future__ import annotations

import base64
import hashlib

from tests.conftest import csrf_headers
from tests.helpers_upload import chunks_for

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/6Z8AAAAASUVORK5CYII="
)
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


def _upload(client, session, data: bytes, filename: str) -> dict:
    init = client.post(
        "/api/v1/uploads",
        json={"filename": filename, "size_bytes": len(data),
              "target_folder_id": None, "chunk_size_mb": 1},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert init.status_code == 201, init.text
    upload_id = init.json()["upload_id"]
    for number, chunk in enumerate(chunks_for(data, 1024 * 1024), start=1):
        saved = client.put(
            f"/api/v1/uploads/{upload_id}/chunks/{number}",
            content=chunk,
            headers={
                **csrf_headers(session["csrf_token"]),
                "X-Chunk-Sha256": hashlib.sha256(chunk).hexdigest(),
            },
        )
        assert saved.status_code == 200, saved.text
    done = client.post(
        f"/api/v1/uploads/{upload_id}/complete", json={},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert done.status_code == 200, done.text
    return done.json()


def test_photo_classification_and_metadata(client, admin_auth):
    session = admin_auth
    photo = _upload(client, session, TINY_PNG, "pixel.png")

    photos = client.get("/api/v1/media/photos").json()
    assert photos["total"] == 1
    item = photos["items"][0]
    assert item["id"] == photo["id"]
    assert item["kind"] == "photo"
    assert item["mime_type"] == "image/png"
    assert item["width"] == 1 and item["height"] == 1
    assert item["gps_stripped"] is True
    assert client.get("/api/v1/media/videos").json()["total"] == 0

    thumb = client.get(f"/api/v1/media/{photo['id']}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.content  # inline original when Pillow is not installed, or a JPEG


def test_video_classification(client, admin_auth):
    session = admin_auth
    video = _upload(client, session, FAKE_MP4, "clip.mp4")
    videos = client.get("/api/v1/media/videos").json()
    assert videos["total"] == 1
    assert videos["items"][0]["id"] == video["id"]
    assert videos["items"][0]["kind"] == "video"
    assert videos["items"][0]["duration_seconds"] is None  # never guessed
    assert client.get("/api/v1/media/photos").json()["total"] == 0


def test_album_crud_and_filtering(client, admin_auth):
    session = admin_auth
    photo = _upload(client, session, TINY_PNG, "album-photo.png")

    create = client.post(
        "/api/v1/albums",
        json={"name": "Holiday", "description": "summer"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert create.status_code == 201, create.text
    album = create.json()
    assert album["name"] == "Holiday"
    assert album["file_count"] == 0

    duplicate = client.post(
        "/api/v1/albums", json={"name": "Holiday"},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert duplicate.status_code == 409

    added = client.post(
        f"/api/v1/albums/{album['id']}/files",
        json={"file_ids": [photo["id"], photo["id"]]},
        headers=csrf_headers(session["csrf_token"]),
    )
    assert added.json()["added"] == 1  # deduplicated

    albums = client.get("/api/v1/albums").json()["items"]
    assert len(albums) == 1
    assert albums[0]["file_count"] == 1
    assert albums[0]["total_bytes"] == len(TINY_PNG)

    filtered = client.get(f"/api/v1/media/photos?album_id={album['id']}").json()
    assert [row["id"] for row in filtered["items"]] == [photo["id"]]

    removed = client.delete(
        f"/api/v1/albums/{album['id']}/files/{photo['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert removed.status_code == 200
    assert client.get(f"/api/v1/media/photos?album_id={album['id']}").json()["total"] == 0

    deleted = client.delete(
        f"/api/v1/albums/{album['id']}",
        headers=csrf_headers(session["csrf_token"]),
    )
    assert deleted.status_code == 200
    assert client.get("/api/v1/albums").json()["items"] == []


def test_media_endpoints_require_auth(client):
    assert client.get("/api/v1/media/photos").status_code == 401
    assert client.get("/api/v1/media/videos").status_code == 401
    assert client.get("/api/v1/albums").status_code == 401
