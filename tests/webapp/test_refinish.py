"""The owner-requested repair for observer #903: give back the finished
pictures a restack flattened — and only those (``webapp.refinish``)."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp import pipeline
from webapp.jobs import Job
from webapp.refinish import (
    AUTO_EDIT_OFF,
    BY_HAND,
    COVER_PINNED,
    NEVER_FINISHED,
    REFINISH,
    refinish_verdict,
    scan_refinish,
)

from .test_reprocess_all import _run_body, _settings

_OPS = [{"id": "tone.stretch", "enabled": True, "params": {"amount": 1.0}}]


def _run(proj, ts: str, *, options: dict | None = None) -> int:
    """A stacked run with a preview (what the wall shows), at an explicit time so
    "newer" and "older" are never a tie."""
    return proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc=ts, output_basename=f"master_{ts[:10]}",
        fits_path=None, tiff_path=None, preview_path=f"/tmp/p_{ts}.png",
        n_frames_used=3, canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=3,
        options_json=json.dumps(options or {"method": "sigma"}), engine_version="0.0.1"))


def _auto_finish(proj, run_id: int) -> None:
    """What the app's own unattended auto-edit leaves on a run: the recipe, the
    baked-look stamp, and the mark that the preview bytes are that render."""
    from webapp.routers.editor import AUTO_EDIT_BAKED_LOOK_PREFIX, RECIPE_META_PREFIX
    from webapp.routers.stack import _recipe_look

    recipe = json.dumps({"ops": _OPS})
    proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", recipe)
    proj.set_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}", json.dumps(_recipe_look(recipe)))
    proj.set_run_preview_display_space(run_id)


def _verdict(lib, safe):
    entry = lib.find_target(safe)
    proj = lib.open_target(safe)
    try:
        return refinish_verdict(proj, entry)
    finally:
        proj.close()


def _first_target(lib):
    return lib.list_targets()[0].safe_name


def test_a_restack_over_an_auto_finished_picture_is_refinished(built_library):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            new = _run(proj, "2026-09-10T00:00:00Z")   # the flat restack now shown
        finally:
            proj.close()
        v = _verdict(lib, safe)
        assert v.verdict == REFINISH and v.run_id == new
    finally:
        lib.close()


def test_a_picture_somebody_finished_by_hand_is_left_alone(built_library):
    """An editor export is a finished picture with no baked-look stamp: Auto's
    look is no evidence of what that person wanted."""
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            _run(proj, "2026-05-01T00:00:00Z",
                 options={"editor_recipe": {"ops": _OPS}, "display_space": "stretched"})
            _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
        assert _verdict(lib, safe).verdict == BY_HAND
    finally:
        lib.close()


def test_a_target_that_was_never_finished_is_left_alone(built_library):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            _run(proj, "2026-05-01T00:00:00Z")
            _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
        assert _verdict(lib, safe).verdict == NEVER_FINISHED
    finally:
        lib.close()


def test_a_saved_but_unrendered_recipe_does_not_count_as_finished(built_library):
    """v0.449.0's rule: saving a recipe re-renders nothing, so that older run was
    never a finished picture — there is nothing to 'give back'."""
    from webapp.routers.editor import RECIPE_META_PREFIX

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            proj.set_meta(f"{RECIPE_META_PREFIX}{old}", json.dumps({"ops": _OPS}))
            _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
        assert _verdict(lib, safe).verdict == NEVER_FINISHED
    finally:
        lib.close()


def test_a_pinned_cover_is_left_alone(built_library):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            new = _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
        lib.set_target_cover(safe, new)   # somebody chose the flat one on purpose
        assert _verdict(lib, safe).verdict == COVER_PINNED
    finally:
        lib.close()


def test_a_target_with_auto_edit_turned_off_is_left_alone(built_library):
    from webapp.auto_edit_pref import write_auto_edit_pref

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            _run(proj, "2026-09-10T00:00:00Z")
            write_auto_edit_pref(proj, False)
        finally:
            proj.close()
        assert _verdict(lib, safe).verdict == AUTO_EDIT_OFF
    finally:
        lib.close()


def test_a_target_already_showing_a_finished_picture_is_not_named(built_library):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            _run(proj, "2026-05-01T00:00:00Z")
            new = _run(proj, "2026-09-10T00:00:00Z")
            _auto_finish(proj, new)
        finally:
            proj.close()
        assert _verdict(lib, safe) is None
        assert scan_refinish(lib) == []
    finally:
        lib.close()


def test_the_job_refinishes_only_the_auto_finished_target(built_library, monkeypatch):
    """Two flat targets: one lost an Auto picture, one lost a hand-finished one.
    Only the first is written to — with the owner's crop preference — and the
    summary names the other and why."""
    calls: list[tuple] = []

    def _fake(lib, safe, run_id, auto_crop=True):  # noqa: ANN001
        calls.append((safe, run_id, auto_crop))
        return 3

    monkeypatch.setattr("webapp.pipeline._auto_edit_process_run", _fake)
    lib = Library.open_or_create(built_library / "library")
    try:
        a, b = [e.safe_name for e in lib.list_targets()][:2]
        pa = lib.open_target(a)
        try:
            old = _run(pa, "2026-05-01T00:00:00Z")
            _auto_finish(pa, old)
            new_a = _run(pa, "2026-09-10T00:00:00Z")
        finally:
            pa.close()
        pb = lib.open_target(b)
        try:
            _run(pb, "2026-05-01T00:00:00Z",
                 options={"editor_recipe": {"ops": _OPS}, "display_space": "stretched"})
            _run(pb, "2026-09-10T00:00:00Z")
        finally:
            pb.close()
        name_b = lib.find_target(b).name
    finally:
        lib.close()

    settings = _settings(built_library)
    settings.auto_crop_border = False
    summary = _run_body(pipeline.submit_refinish_pictures, settings, Job(kind="refinish_pictures"))

    assert calls == [(a, new_a, False)]
    assert len(summary["refinished"]) == 1 and summary["failed"] == []
    assert summary["left_alone"] == {BY_HAND: [name_b]}


def test_a_stand_down_by_the_writer_is_reported_not_counted(built_library, monkeypatch):
    """``_auto_edit_process_run`` returns None when it refuses (no FITS, or a
    recipe it did not bake appeared). That is reported, never counted as done."""
    monkeypatch.setattr("webapp.pipeline._auto_edit_process_run",
                        lambda *a, **k: None)
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
    finally:
        lib.close()
    summary = _run_body(pipeline.submit_refinish_pictures, _settings(built_library),
                        Job(kind="refinish_pictures"))
    assert summary["refinished"] == []
    assert len(summary["failed"]) == 1 and "skipped" in summary["failed"][0]["error"]


def test_preview_endpoint_names_both_groups_and_writes_nothing(built_library, client):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            new = _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
    finally:
        lib.close()
    r = client.get("/api/unstretched-pictures/refinish")
    assert r.status_code == 200
    body = r.json()
    assert [t["safe_name"] for t in body["refinish"]] == [safe]
    # Read-only: the flat run still has no recipe.
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            from webapp.routers.editor import RECIPE_META_PREFIX
            assert proj.get_meta(f"{RECIPE_META_PREFIX}{new}") is None
        finally:
            proj.close()
    finally:
        lib.close()


def test_start_endpoint_queues_one_job(client):
    r1 = client.post("/api/unstretched-pictures/refinish")
    assert r1.status_code == 200 and r1.json()["job_id"]
