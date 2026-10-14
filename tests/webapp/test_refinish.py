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


# --------------------------------------------------------------------------- #
# Who pinned the cover (v0.492.13's ``seestack.coverpin``)
# --------------------------------------------------------------------------- #

def _app_pin(lib, safe: str, run_id: int, reason: str) -> None:
    """Pin a cover the way the app's own code does — the registry column plus the
    record saying it was us. ``Library.merge_targets_result`` does exactly this
    pair after a Combine."""
    from seestack.coverpin import mark_app_pin

    lib.set_target_cover(safe, run_id)
    proj = lib.open_target(safe)
    try:
        mark_app_pin(proj, run_id, reason)
    finally:
        proj.close()


def test_a_cover_the_app_pinned_during_a_combine_is_still_repairable(built_library):
    """A Combine pins whatever the destination was *showing*, finished or flat
    (``_displayed_run_id`` deliberately never asks), so a target combined while
    its picture was flat was beyond this repair — and the summary told the owner
    he had chosen that picture. Only a pin *he* placed means that."""
    from seestack.coverpin import PIN_REASON_MERGE

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            flat = _run(proj, "2026-09-10T00:00:00Z")
            _run(proj, "2026-09-20T00:00:00Z")      # the night a Combine carried in
        finally:
            proj.close()
        _app_pin(lib, safe, flat, PIN_REASON_MERGE)
        v = _verdict(lib, safe)
        # The pinned run is the displayed one, so it is the run a repair bakes.
        assert v.verdict == REFINISH and v.run_id == flat
    finally:
        lib.close()


def test_an_app_pin_falls_through_to_the_rest_of_the_ladder(built_library):
    """Lifting the cover stand-down for an app pin must not jump straight to a
    repair: the pinned picture is judged on the same evidence as any other flat
    one, so an older picture somebody finished by hand is still left alone."""
    from seestack.coverpin import PIN_REASON_MERGE

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            _run(proj, "2026-05-01T00:00:00Z",
                 options={"editor_recipe": {"ops": _OPS}, "display_space": "stretched"})
            flat = _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
        _app_pin(lib, safe, flat, PIN_REASON_MERGE)
        assert _verdict(lib, safe).verdict == BY_HAND
    finally:
        lib.close()


def test_his_own_pin_is_left_alone_even_when_a_stale_app_record_exists(built_library):
    """``app_pin_reason``'s retirement rule, asserted at this seam: a record that
    names a run other than the one pinned is not about this pin, so the pin is
    his and the target is still left alone — no code had to notice he re-pinned."""
    from seestack.coverpin import PIN_REASON_MERGE, mark_app_pin

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            flat = _run(proj, "2026-09-10T00:00:00Z")
            other = _run(proj, "2026-09-20T00:00:00Z")
            mark_app_pin(proj, other, PIN_REASON_MERGE)   # about a pin that is gone
        finally:
            proj.close()
        lib.set_target_cover(safe, flat)                  # he chose the flat one
        assert _verdict(lib, safe).verdict == COVER_PINNED
    finally:
        lib.close()


def test_a_kept_finished_pin_never_reaches_the_cover_test(built_library):
    """Why only the Combine reason needed fixing: ``kept_finished`` is placed on a
    *finished* picture, so the target is not one of the flat ones at all and the
    function has answered ``None`` before the cover is ever looked at."""
    from seestack.coverpin import PIN_REASON_KEPT_FINISHED

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            kept = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, kept)
            _run(proj, "2026-09-10T00:00:00Z")
        finally:
            proj.close()
        _app_pin(lib, safe, kept, PIN_REASON_KEPT_FINISHED)
        assert _verdict(lib, safe) is None
        assert scan_refinish(lib) == []
    finally:
        lib.close()


def test_the_job_repairs_a_target_the_app_pinned(built_library, monkeypatch):
    """End to end: the repair writes to a Combine-pinned flat target, and bakes
    the pinned run rather than the newest one."""
    from seestack.coverpin import PIN_REASON_MERGE

    calls: list[tuple] = []

    def _fake(lib, safe, run_id, auto_crop=True):  # noqa: ANN001
        calls.append((safe, run_id, auto_crop))
        return 3

    monkeypatch.setattr("webapp.pipeline._auto_edit_process_run", _fake)
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        proj = lib.open_target(safe)
        try:
            old = _run(proj, "2026-05-01T00:00:00Z")
            _auto_finish(proj, old)
            flat = _run(proj, "2026-09-10T00:00:00Z")
            _run(proj, "2026-09-20T00:00:00Z")
        finally:
            proj.close()
        _app_pin(lib, safe, flat, PIN_REASON_MERGE)
    finally:
        lib.close()

    summary = _run_body(pipeline.submit_refinish_pictures, _settings(built_library),
                        Job(kind="refinish_pictures"))
    assert calls == [(safe, flat, True)]
    assert len(summary["refinished"]) == 1
    assert summary["failed"] == [] and summary["left_alone"] == {}
