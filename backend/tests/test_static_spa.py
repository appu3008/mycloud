"""Single-origin deployment: SPA fallback must not shadow API routes."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT

DIST = PROJECT_ROOT / "frontend-rs" / "dist"


@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="frontend build not present")
def test_client_routes_serve_index(client):
    for path in ("/", "/files", "/share/a-token", "/settings"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "<html" in response.text.lower(), path


@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="frontend build not present")
def test_api_routes_are_not_shadowed(client):
    assert client.get("/api/health").status_code == 200
    unknown = client.get("/api/v1/definitely-missing")
    assert unknown.status_code == 404
    assert "detail" in unknown.json()


@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="frontend build not present")
def test_static_assets_are_served(client):
    css = next((DIST / "assets").glob("*.css"), None) if (DIST / "assets").is_dir() else None
    if css is None:
        pytest.skip("no CSS asset in build")
    response = client.get(f"/assets/{Path(css).name}")
    assert response.status_code == 200
    assert "css" in response.headers.get("content-type", "")
