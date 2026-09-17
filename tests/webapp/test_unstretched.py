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
    """Bake a finished look into a run's preview, the way an in-place auto-edit
    does: the recipe **and** the ``preview_display_space`` mark that says the
    stored bytes are that recipe's render rather than the linear autostretch.

    Both halves, because only the second one is what makes the picture finished
    — see ``_save_only`` for the other case, and
    ``webapp.finishedpicture.run_is_a_finished_picture``."""
    proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", json.dumps({"ops": ops or _OPS}))
    proj.set_run_preview_display_space(run_id)


def _save_only(proj, run_id, ops=None):
    """A recipe somebody **saved in the editor and never baked** — which is what
    Save does and all it does: ``put_recipe`` writes the row and re-renders
    nothing, so the run's preview is still the plain autostretch of its linear
    master and the picture on the wall has not changed."""
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


# --------------------------------------------------------------------------- #
# The Gallery's per-run half of the same answer (`GalleryItem.finished`)
#
# The endpoint above answers per *target*, about the one run it displays. The
# Gallery lists every run of every target, so reusing that answer here would
# badge the displayed run correctly and say nothing at all about the older linear
# runs beside it — on the page whose whole job is looking at pictures.
# --------------------------------------------------------------------------- #

def test_the_gallery_answers_finished_per_run_not_per_target(
        solved_client, solved_library):
    """A target holding one edited run and one linear run gets one of each
    answer — which is the thing the per-target endpoint structurally cannot say."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            old = _seed(proj, basename="master")
            _edit(proj, old)
            fresh = _seed(proj, basename="master_v2")   # no recipe: linear
        finally:
            proj.close()
    finally:
        lib.close()

    items = solved_client.get("/api/gallery").json()["items"]
    by_run = {i["run_id"]: i for i in items}
    assert by_run[old]["finished"] is True
    assert by_run[fresh]["finished"] is False
    # …and the per-target endpoint names the target, because the run it *shows*
    # (the newest with a preview) is the linear one. The two are consistent, and
    # the Gallery's is the finer-grained answer.
    named = [i["safe"] for i in
             solved_client.get("/api/unstretched-pictures").json()["items"]]
    assert named == [safe]


def test_the_gallery_and_the_wall_agree_about_the_displayed_run(
        solved_client, solved_library):
    """One definition, two surfaces: for the run the wall is judging, the
    Gallery's per-run `finished` is the negation of being named unstretched."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        a, b = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(a)
        try:
            _edit(proj, _seed(proj))            # finished
        finally:
            proj.close()
        proj = lib.open_target(b)
        try:
            _seed(proj)                          # linear
        finally:
            proj.close()
    finally:
        lib.close()

    named = {i["safe"] for i in
             solved_client.get("/api/unstretched-pictures").json()["items"]}
    assert named == {b}
    items = solved_client.get("/api/gallery").json()["items"]
    # Each target has exactly one run here, so each run *is* its displayed picture.
    for it in items:
        assert it["finished"] is (it["safe"] not in named), it


def test_the_gallery_counts_an_editor_export_as_finished(
        solved_client, solved_library):
    """Same second shape the wall honours: an export's stacked pixels are already
    tone-mapped, so its preview is a picture in its own right even with no recipe
    saved against it."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            run_id = _seed(proj, basename="export",
                           options={"editor_recipe": {"ops": _OPS},
                                    "display_space": True})
        finally:
            proj.close()
    finally:
        lib.close()

    items = solved_client.get("/api/gallery").json()["items"]
    assert next(i for i in items if i["run_id"] == run_id)["finished"] is True


def test_an_all_disabled_recipe_is_not_a_finished_gallery_card(
        solved_client, solved_library):
    """A recipe whose every op is off renders the linear stack, so the card must
    say so — the same arm the wall already pins, asserted here because this is a
    second call site of the shared rule rather than a second rule."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            run_id = _seed(proj)
            _edit(proj, run_id,
                  ops=[{"id": "tone.curves", "enabled": False, "params": {}}])
        finally:
            proj.close()
    finally:
        lib.close()

    items = solved_client.get("/api/gallery").json()["items"]
    assert next(i for i in items if i["run_id"] == run_id)["finished"] is False


def test_the_two_finished_picture_forms_answer_identically(solved_library):
    """`run_is_a_finished_picture_from` exists only so the Gallery can answer off
    a column it has already selected; it must never become a second definition."""
    from webapp.finishedpicture import (
        run_is_a_finished_picture,
        run_is_a_finished_picture_from,
    )

    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            plain = _seed(proj)
            edited = _seed(proj, basename="m2")
            _edit(proj, edited)
            saved_only = _seed(proj, basename="m3")
            _save_only(proj, saved_only)
            export = _seed(proj, basename="m4",
                           options={"editor_recipe": {"ops": _OPS}})
            for run in proj.iter_stack_runs():
                recipe = proj.get_meta(f"{RECIPE_META_PREFIX}{run.id}")
                assert run_is_a_finished_picture(proj, run) is (
                    run_is_a_finished_picture_from(run.options_json, recipe)), run.id
            # …and the expected answers, so an "identical" that is identically
            # wrong cannot pass.
            answers = {r.id: run_is_a_finished_picture(proj, r)
                       for r in proj.iter_stack_runs()}
            assert answers[plain] is False
            assert answers[edited] is True
            # The one the old rule got backwards: a recipe nothing baked leaves
            # the preview exactly as it was.
            assert answers[saved_only] is False
            assert answers[export] is True
        finally:
            proj.close()
    finally:
        lib.close()


def test_saving_an_edit_does_not_make_an_unstretched_card_look_finished(
        solved_client, solved_library):
    """Regression (v0.449.0): the chip used to **vanish** when a user saved an
    edit, on a card whose bytes had not changed.

    ``put_recipe`` writes the recipe row and re-renders nothing, so the wall is
    still showing ``_write_preview_png``'s autostretch of the linear master —
    and the app says so itself, on the same screens, through
    ``unexported_edit``. Withdrawing the chip there is exactly backwards: that
    picture is unstretched *and* the user's work is invisible on it."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        saved_only, baked = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(saved_only)
        try:
            _save_only(proj, _seed(proj))
        finally:
            proj.close()
        proj = lib.open_target(baked)
        try:
            _edit(proj, _seed(proj))
        finally:
            proj.close()
    finally:
        lib.close()

    body = solved_client.get("/api/unstretched-pictures").json()
    assert [i["safe"] for i in body["items"]] == [saved_only]
    # The Gallery's per-run chip is the same rule, so it cannot say the opposite
    # about the very same run — which is what made this findable.
    items = solved_client.get("/api/gallery").json()["items"]
    by_target = {i["safe"]: i["finished"] for i in items}
    assert by_target[saved_only] is False
    assert by_target[baked] is True


def test_an_unstretched_card_says_which_kind_of_unstretched_it_is(
        solved_client, solved_library):
    """Both cards get the chip, and only one of them should be told to press
    Auto.

    A card unstretched because nobody has edited it wants "open it and press
    Auto"; a card unstretched because its owner's edit was never exported wants
    the opposite, since Auto replaces a saved recipe. The wall could not tell
    them apart because the item carried no such fact — the Gallery's own card
    has carried ``unexported_edit`` all along."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        untouched, saved_only = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(untouched)
        try:
            _seed(proj)
        finally:
            proj.close()
        proj = lib.open_target(saved_only)
        try:
            _save_only(proj, _seed(proj))
        finally:
            proj.close()
    finally:
        lib.close()

    items = {i["safe"]: i for i in
             solved_client.get("/api/unstretched-pictures").json()["items"]}
    assert set(items) == {untouched, saved_only}
    assert items[untouched]["unexported_edit"] is False
    assert items[saved_only]["unexported_edit"] is True


def test_the_wall_and_the_gallery_agree_about_an_unexported_edit(
        solved_client, solved_library):
    """One predicate, two surfaces: the Gallery has reported this state per run
    since before the wall did, and the two must not name different pictures."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(e.safe_name for e in lib.list_targets())
        proj = lib.open_target(safe)
        try:
            run_id = _seed(proj)
            _save_only(proj, run_id)
        finally:
            proj.close()
    finally:
        lib.close()

    wall = solved_client.get("/api/unstretched-pictures").json()["items"]
    gallery = solved_client.get("/api/gallery").json()["items"]
    assert next(i for i in wall if i["safe"] == safe)["unexported_edit"] is (
        next(i for i in gallery if i["run_id"] == run_id)["unexported_edit"])
    assert next(i for i in wall if i["safe"] == safe)["unexported_edit"] is True


def test_the_reprocess_warning_stops_counting_a_saved_only_edit_as_finished(
        solved_client, solved_library):
    """The third surface off the same definition: the "Reprocess everything"
    dialog warns how many finished pictures an unedited restack would replace.

    A target whose newest run merely carries a saved recipe has nothing to
    replace — its card is already the linear autostretch — so counting it
    inflated the warning that exists to be believed."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        saved_only, baked = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(saved_only)
        try:
            _save_only(proj, _seed(proj))
        finally:
            proj.close()
        proj = lib.open_target(baked)
        try:
            _edit(proj, _seed(proj))
        finally:
            proj.close()
    finally:
        lib.close()

    status = solved_client.get("/api/reprocess-status").json()
    assert status["finished_pictures"] == 1
