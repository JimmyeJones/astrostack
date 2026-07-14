"""End-to-end tests for the production-only SPA-serving wiring.

The dev/test tree has no ``webapp/static`` dir, so the SPA fallback route, the
``/assets`` StaticFiles mount, and — crucially — how the auth-gate middleware
interacts with static/asset requests are **only** wired up in the shipped Docker
image and were never exercised end-to-end by any test. That blind spot is exactly
how the v0.109.24 path-traversal hole reached production unnoticed.

``test_spa_static.py`` pins the traversal contract of ``spa`` in isolation; this
module boots the **full** ``create_app()`` (routers + auth middleware + lifespan)
over a materialised static tree and asserts the prod-only wiring holds together:
the shell + assets serve, traversal is blocked through the whole stack, and the
auth gate covers static/asset requests (while ``/api/health`` stays open).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webapp import main


@pytest.fixture
def static_client(data_root: Path, monkeypatch):
    """A TestClient over the full app, with a fake production static dir mounted.

    Mirrors the ``client`` fixture but materialises ``webapp/static`` and patches
    ``main.STATIC_DIR`` *before* ``create_app()`` so ``_mount_spa`` installs the
    real serving path (not the dev placeholder). Returns ``(client, tmp_path)``.
    """
    static = data_root / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA-SHELL</html>")
    (static / "assets" / "app.js").write_text("console.log('legit')")
    # A secret sitting *outside* the static root — never web-servable.
    (data_root / "SECRET.txt").write_text("TOPSECRET-hash")

    monkeypatch.setenv("ASTROSTACK_DATA", str(data_root))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    monkeypatch.setattr(main, "STATIC_DIR", static)

    app = main.create_app()
    with TestClient(app) as c:
        c.put("/api/settings", json={"watcher_enabled": False})
        yield c, data_root


def test_shell_and_client_routes_serve_through_full_app(static_client):
    """`/` and an unknown client route return the SPA shell through the full
    router + middleware stack (not the dev 'Frontend not built' placeholder)."""
    client, _ = static_client
    root = client.get("/")
    assert root.status_code == 200 and "SPA-SHELL" in root.text
    deep = client.get("/targets/some-id/editor")
    assert deep.status_code == 200 and "SPA-SHELL" in deep.text


def test_real_asset_serves_through_assets_mount(static_client):
    """A real asset serves from the ``/assets`` StaticFiles mount."""
    client, _ = static_client
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "legit" in r.text


def test_api_routes_still_win_over_the_spa_catch_all(static_client):
    """The SPA catch-all must not shadow the real API routes."""
    client, _ = static_client
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "SPA-SHELL" not in r.text


def test_traversal_blocked_through_full_stack(static_client):
    """A percent-encoded ``../`` escape falls back to the shell — never the
    out-of-root secret — even with the whole app (middleware + routers) wired."""
    client, _ = static_client
    for path in ("/%2e%2e/SECRET.txt", "/../SECRET.txt", "/SECRET.txt"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "TOPSECRET" not in r.text, path
        assert "SPA-SHELL" in r.text, path


def test_auth_gate_covers_static_and_assets_but_not_health(static_client):
    """With auth on, unauthenticated static/asset requests are challenged with a
    401 (the browser then retries with credentials); the Docker healthcheck path
    stays open. This is the prod-only middleware↔static interaction no test
    previously exercised."""
    client, _ = static_client
    r = client.post("/api/auth/password", json={"password": "secret1", "username": "pilot"})
    assert r.status_code == 200 and r.json()["enabled"] is True

    try:
        # The SPA shell and its assets are gated just like the API.
        for path in ("/", "/targets/x/editor", "/assets/app.js"):
            unauth = client.get(path)
            assert unauth.status_code == 401, path
            assert "Basic" in unauth.headers.get("WWW-Authenticate", ""), path
            # A traversal attempt is *also* gated (never leaks even pre-auth).
            assert "TOPSECRET" not in unauth.text, path

        # Correct credentials serve the real content.
        assert "SPA-SHELL" in client.get("/", auth=("pilot", "secret1")).text
        assert "legit" in client.get("/assets/app.js", auth=("pilot", "secret1")).text

        # The healthcheck stays reachable without credentials.
        assert client.get("/api/health").status_code == 200
    finally:
        # Leave auth disabled so the shared app teardown is clean.
        client.post("/api/auth/password", json={"password": ""}, auth=("pilot", "secret1"))
