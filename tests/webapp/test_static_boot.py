"""The app must boot even when the built frontend is missing or half-written.

AstroStack is upgraded **in place** on a live TrueNAS box (AGENTS.md §9), and one
of that section's hard requirements is that the container still boots. Until
v0.413.2 it did not, in one reachable state: ``_mount_spa`` decided "is the
frontend built?" from ``STATIC_DIR.exists()`` — the *directory* — and then
mounted ``static/assets`` unconditionally. ``vite build`` sets ``emptyOutDir``,
so it **deletes that tree before writing it**; an interrupted build, or a
half-copied image layer, leaves the directory there and its contents gone. In
that state Starlette raised ``RuntimeError: Directory '…/static/assets' does not
exist`` out of ``create_app()``, so the API, the Settings page and the job queue
all refused to start over a missing *frontend*.

Reproduced 14 times in one run (2026-09-10) by a pytest session that happened to
overlap a ``vite build`` — which is exactly the shape of an upgrade landing while
something else is reading the tree.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webapp import main


def _mounted(static, monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "STATIC_DIR", static)
    app = FastAPI()
    main._mount_spa(app)
    return TestClient(app)


def test_an_emptied_static_dir_still_boots_and_says_the_frontend_is_not_built(
        tmp_path, monkeypatch):
    """The state a `vite build` passes through: the dir is there, nothing in it."""
    static = tmp_path / "static"
    static.mkdir()          # emptyOutDir has deleted the contents, not the dir

    client = _mounted(static, monkeypatch)   # fails before: RuntimeError at mount

    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["message"] == "AstroStack API is running. Frontend not built."


def test_a_static_dir_with_assets_but_no_index_is_also_not_built(tmp_path, monkeypatch):
    """`assets/` alone is not a frontend: serving the SPA shell would 500 on
    every client route, so this must take the placeholder branch too."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "assets" / "app.js").write_text("console.log('orphan')")

    client = _mounted(static, monkeypatch)

    assert client.get("/").json()["message"].endswith("Frontend not built.")


def test_an_index_without_an_assets_dir_still_serves_the_app(tmp_path, monkeypatch):
    """The mount is now conditional — and nothing is lost when it is skipped,
    because the SPA catch-all already serves any file under the static root."""
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>SPA-SHELL</html>")
    (static / "favicon.ico").write_text("ICON")

    client = _mounted(static, monkeypatch)   # fails before: RuntimeError at mount

    assert "SPA-SHELL" in client.get("/library").text
    assert client.get("/favicon.ico").text == "ICON"


def test_a_complete_build_is_served_exactly_as_before(tmp_path, monkeypatch):
    """The ordinary case is untouched: `/assets` is mounted and serves its own
    files, and an unknown client route still falls back to the shell."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA-SHELL</html>")
    (static / "assets" / "app.js").write_text("console.log('legit')")

    client = _mounted(static, monkeypatch)

    assert client.get("/assets/app.js").text == "console.log('legit')"
    assert "SPA-SHELL" in client.get("/targets/M42").text


@pytest.mark.parametrize("missing", ["assets", "index"])
def test_whatever_is_missing_the_app_answers_instead_of_erroring(
        tmp_path, monkeypatch, missing):
    """The one thing an owner watching a container restart cannot act on is a
    server error, so neither half-built state may produce one.

    Note the two *are* different answers, deliberately: with `index.html` there
    the SPA shell is served for any client route; without it there is no page to
    serve, so an unknown route is an honest 404 while `/` explains why. Neither
    is a 5xx, and neither stops `create_app()`.
    """
    static = tmp_path / "static"
    static.mkdir()
    if missing == "assets":
        (static / "index.html").write_text("<html>SPA-SHELL</html>")
    else:
        (static / "assets").mkdir()

    client = _mounted(static, monkeypatch)

    assert client.get("/").status_code == 200
    assert client.get("/library").status_code < 500
