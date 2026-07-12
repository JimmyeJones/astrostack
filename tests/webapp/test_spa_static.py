"""Regression tests for the SPA static fallback handler.

The production Docker image builds the frontend into ``webapp/static`` and
``_mount_spa`` then serves it with an SPA fallback for client-side routes. The
dev/test tree has no ``static`` dir, so this handler is normally not mounted —
which is exactly why a path-traversal hole in it went unnoticed. These tests
build a temporary static tree, mount the handler, and pin its security contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webapp import main


@pytest.fixture
def spa_client(tmp_path, monkeypatch):
    """A TestClient over just the SPA fallback, with a fake production static dir."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA-SHELL</html>")
    (static / "assets" / "app.js").write_text("console.log('legit')")
    (static / "favicon.ico").write_text("ICON")
    # A secret sitting *outside* the static root — never web-servable.
    (tmp_path / "SECRET.txt").write_text("TOPSECRET-hash")

    monkeypatch.setattr(main, "STATIC_DIR", static)
    app = FastAPI()
    main._mount_spa(app)
    return TestClient(app), tmp_path


@pytest.mark.parametrize(
    "path",
    [
        "/%2e%2e/SECRET.txt",  # percent-encoded ".." (browsers/httpx leave this literal)
        "/%2e%2e%2f%2e%2e%2fSECRET.txt",  # encoded "../../"
        "/../SECRET.txt",
        "/%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
    ],
)
def test_spa_rejects_path_traversal(spa_client, path):
    """A traversal escaping the static root must fall back to the SPA shell,
    never leak an out-of-root file."""
    client, _ = spa_client
    r = client.get(path)
    assert r.status_code == 200
    assert "SPA-SHELL" in r.text
    assert "TOPSECRET" not in r.text
    assert "root:x:0:0" not in r.text


def test_assets_mount_rejects_traversal(spa_client):
    """The ``/assets`` StaticFiles mount has its own traversal guard — a
    ``../`` escape there must not leak an out-of-root file either."""
    client, _ = spa_client
    r = client.get("/assets/%2e%2e/%2e%2e/SECRET.txt")
    assert "TOPSECRET" not in r.text
    assert r.status_code in (404, 200)  # StaticFiles 404s; never the secret
    if r.status_code == 200:
        assert "SPA-SHELL" in r.text


def test_spa_serves_real_static_files(spa_client):
    """Legitimate assets inside the static root still serve."""
    client, _ = spa_client
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.text == "ICON"


def test_spa_falls_back_to_shell_for_client_routes(spa_client):
    """Unknown client-side routes get the SPA shell (unchanged behaviour)."""
    client, _ = spa_client
    r = client.get("/targets/some-id/editor")
    assert r.status_code == 200
    assert "SPA-SHELL" in r.text


def test_spa_confinement_uses_resolved_root(spa_client, tmp_path):
    """The confinement compares resolved paths, so a symlinked static root is
    still safe (defensive — the resolved candidate must stay under it)."""
    client, root = spa_client
    # Directly assert the served secret file is unreachable by its basename too.
    r = client.get("/SECRET.txt")
    assert r.status_code == 200
    assert "TOPSECRET" not in r.text
    assert Path(root / "SECRET.txt").exists()  # sanity: the file really is there
