"""The "Not stretched yet" answer: which targets show a flat linear stack.

A linear master and a finished auto-edit are the same rectangle at 160 px, one
with its histogram stretched and one without, so the Library wall could not tell
them apart and neither can a beginner. ``GET /api/unstretched-pictures`` is the
app saying which is which.

Its definition of "finished" is shared with the reprocess dialog's warning
(``webapp.finishedpicture``), and one of the tests below pins that they agree —
two surfaces naming different targets for the same word is the drift this
codebase keeps undoing.
"""

from __future__ import annotations

import json

import pytest

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp.routers.editor import RECIPE_META_PREFIX

_OPS = [{"id": "tone.curves", "enabled": True, "params": {}}]


@pytest.fixture
def solved_client(solved_library, monkeypatch):
    """A TestClient over the two-target solved fixture — the same shape
    ``test_reprocess_all.py`` uses, because this endpoint's whole subject is a
    library with real targets in it."""
    monkeypatch.setenv("ASTROSTACK_DATA", str(solved_library))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    from fastapi.testclient import TestClient

    from webapp.main import create_app

    app = create_app()
    with TestClient(app) as c:
        c.put("/api/settings", json={"watcher_enabled": False})
        yield c


def _seed(proj, *, basename="master", preview="p.png", options=None):
    proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc="2026-05-01T00:00:00Z",
        output_basename=basename, fits_path=None, tiff_path=None,
        preview_path=preview, n_frames_used=3, canvas_h=10, canvas_w=10,
        coverage_min=1, coverage_max=3,
        options_json=json.dumps(options or {"method": "sigma", "sigma_kappa": 4.25}),
        engine_version="0.1.0",
    ))
    return max(r.id for r in proj.iter_stack_runs())


def _edit(proj, run_id, ops=None):
    proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", json.dumps({"ops": ops or _OPS}))


def test_it_names_the_target_showing_a_linear_stack_and_not_the_finished_one(
        solved_client, solved_library):
    lib = Library.open_or_create(solved_library / "library")
    try:
        flat, finished = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(flat)
        try:
            _seed(proj)
        finally:
            proj.close()
        proj = lib.open_target(finished)
        try:
            _edit(proj, _seed(proj))
        finally:
            proj.close()
    finally:
        lib.close()

    body = solved_client.get("/api/unstretched-pictures").json()
    assert body["count"] == 1
    assert [i["safe"] for i in body["items"]] == [flat]
    assert body["items"][0]["run_id"] > 0
    assert body["items"][0]["target_name"]


def test_a_target_with_no_picture_yet_is_not_named(solved_client, solved_library):
    """Nothing to stretch. "Get some more subs" is a different sentence, and the
    Target page already says it — a chip here would be the wrong advice."""
    body = solved_client.get("/api/unstretched-pictures").json()
    assert body["count"] == 0
    assert body["items"] == []


def test_a_run_with_no_preview_is_not_the_displayed_picture(
        solved_client, solved_library):
    """A run that never rendered a preview is not what any wall is showing, so
    the newest run *with* one decides — and here that one is finished."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            _edit(proj, _seed(proj, basename="older"))
            _seed(proj, basename="newest", preview=None)
        finally:
            proj.close()
    finally:
        lib.close()

    assert solved_client.get("/api/unstretched-pictures").json()["count"] == 0


def test_a_newer_linear_run_supersedes_an_older_edited_one(
        solved_client, solved_library):
    """The picture on the wall is the newest run with a preview — which is how
    observer issue #903 left 44 targets looking flat at once."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            _edit(proj, _seed(proj, basename="edited"))
            _seed(proj, basename="restacked")
        finally:
            proj.close()
    finally:
        lib.close()

    body = solved_client.get("/api/unstretched-pictures").json()
    assert [i["safe"] for i in body["items"]] == [safe]


def test_a_pinned_cover_decides_what_is_being_shown(solved_client, solved_library):
    """…and pinning the edited run as the cover makes the wall show it again, so
    the chip has to withdraw. Same rule as ``current_picture_path``."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            edited = _seed(proj, basename="edited")
            _edit(proj, edited)
            _seed(proj, basename="restacked")
        finally:
            proj.close()
        lib.set_target_cover(safe, edited)
    finally:
        lib.close()

    assert solved_client.get("/api/unstretched-pictures").json()["count"] == 0


def test_an_all_disabled_recipe_still_renders_the_linear_stack(
        solved_client, solved_library):
    """A saved recipe whose ops are all off (or all stale) shows exactly the
    flat stack, so it must not count as finished."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            _edit(proj, _seed(proj),
                  ops=[{"id": "tone.curves", "enabled": False, "params": {}}])
        finally:
            proj.close()
    finally:
        lib.close()

    assert solved_client.get("/api/unstretched-pictures").json()["count"] == 1


def test_an_editor_export_is_a_finished_picture(solved_client, solved_library):
    """Its pixels are already tone-mapped, so its preview *is* the picture even
    though no recipe is saved against the run."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            _seed(proj, basename="master_edit",
                  options={"editor_recipe": {"ops": _OPS}, "display_space": True})
        finally:
            proj.close()
    finally:
        lib.close()

    assert solved_client.get("/api/unstretched-pictures").json()["count"] == 0


def test_the_chip_and_the_reprocess_warning_never_name_different_targets(
        solved_client, solved_library):
    """One definition, two surfaces. ``reprocess_status`` counts the targets a
    restack would *take a finished picture away from*; this endpoint names the
    ones already without one. On a library where every target has a picture the
    two must partition it exactly — if they ever drift, one of the two screens
    is lying about the same target."""
    from webapp import pipeline

    lib = Library.open_or_create(solved_library / "library")
    try:
        flat, finished = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(flat)
        try:
            _seed(proj)
        finally:
            proj.close()
        proj = lib.open_target(finished)
        try:
            _edit(proj, _seed(proj))
        finally:
            proj.close()
        status = pipeline.reprocess_status(lib)
    finally:
        lib.close()

    body = solved_client.get("/api/unstretched-pictures").json()
    assert status["finished_pictures"] == 1
    assert body["count"] == 1
    assert status["finished_pictures"] + body["count"] == status["total_targets"]


def test_one_broken_project_does_not_cost_the_whole_answer(
        solved_client, solved_library, monkeypatch):
    """A cross-target read on a wall must degrade, never 500 — the same rule the
    over-trim and new-subs scans follow."""
    from seestack.io.project import Project

    lib = Library.open_or_create(solved_library / "library")
    try:
        good, bad = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(good)
        try:
            _seed(proj)
        finally:
            proj.close()
        bad_dir = str(lib.target_dir(lib.find_target(bad)))
    finally:
        lib.close()

    real_open = Project.open

    def flaky(path, *a, **kw):  # noqa: ANN001, ANN202
        if str(path) == bad_dir:
            raise OSError("database is locked")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(Project, "open", staticmethod(flaky))  # noqa: PT008
    r = solved_client.get("/api/unstretched-pictures")
    assert r.status_code == 200
    assert [i["safe"] for i in r.json()["items"]] == [good]
