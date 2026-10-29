"""The owner's ⭐ entry of 2026-10-28, part 2: one action that finishes every
picture he never edited — and only those (``webapp.finishunedited``)."""

from __future__ import annotations

import json

import pytest

from seestack.io.library import Library
from webapp import pipeline
from webapp.finishunedited import (
    AUTO_EDIT_OFF,
    COVER_PINNED,
    FINISH,
    HAS_EDIT,
    finish_verdict,
    scan_finish_unedited,
)
from webapp.jobs import Job

from .test_refinish import _OPS, _app_pin, _auto_finish, _first_target, _run
from .test_reprocess_all import _run_body, _settings


def _verdict(lib, safe):
    entry = lib.find_target(safe)
    proj = lib.open_target(safe)
    try:
        return finish_verdict(proj, entry)
    finally:
        proj.close()


def _with_project(lib, safe, fn):
    proj = lib.open_target(safe)
    try:
        return fn(proj)
    finally:
        proj.close()


def test_a_never_edited_picture_is_finished(built_library):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        shown = _with_project(lib, safe, lambda p: (
            _run(p, "2026-05-01T00:00:00Z"), _run(p, "2026-09-10T00:00:00Z"))[1])
        v = _verdict(lib, safe)
        assert v.verdict == FINISH and v.run_id == shown
    finally:
        lib.close()


def test_an_already_finished_picture_is_not_named(built_library):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)

        def setup(p):
            _auto_finish(p, _run(p, "2026-09-10T00:00:00Z"))
        _with_project(lib, safe, setup)
        assert _verdict(lib, safe) is None
        assert all(v.safe_name != safe for v in scan_finish_unedited(lib))
    finally:
        lib.close()


def test_an_editor_export_is_not_named(built_library):
    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        _with_project(lib, safe, lambda p: _run(
            p, "2026-09-10T00:00:00Z",
            options={"editor_recipe": {"ops": _OPS}, "display_space": "stretched"}))
        assert _verdict(lib, safe) is None
    finally:
        lib.close()


@pytest.mark.parametrize("ops", [_OPS, [{"id": "tone.stretch", "enabled": False, "params": {}}]])
def test_a_saved_edit_is_never_finished_over(built_library, ops):
    """Any saved recipe is somebody's look — even an all-disabled one, which
    still renders the linear stack and so still reads as unstretched."""
    from webapp.routers.editor import RECIPE_META_PREFIX

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)

        def setup(p):
            rid = _run(p, "2026-09-10T00:00:00Z")
            p.set_meta(f"{RECIPE_META_PREFIX}{rid}", json.dumps({"ops": ops}))
        _with_project(lib, safe, setup)
        assert _verdict(lib, safe).verdict == HAS_EDIT
    finally:
        lib.close()


def test_a_cover_he_pinned_is_left_alone_but_an_app_pin_is_not(built_library):
    from seestack.coverpin import PIN_REASON_MERGE

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        old = _with_project(lib, safe, lambda p: (
            _run(p, "2026-05-01T00:00:00Z"), _run(p, "2026-09-10T00:00:00Z"))[0])
        lib.set_target_cover(safe, old)
        assert _verdict(lib, safe).verdict == COVER_PINNED
        _app_pin(lib, safe, old, PIN_REASON_MERGE)
        v = _verdict(lib, safe)
        # The pinned run is the displayed one, so it is the run a finish bakes.
        assert v.verdict == FINISH and v.run_id == old
    finally:
        lib.close()


def test_a_target_with_auto_edit_off_is_left_alone(built_library):
    from webapp.auto_edit_pref import AUTO_EDIT_META_KEY

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)

        def setup(p):
            _run(p, "2026-09-10T00:00:00Z")
            p.set_meta(AUTO_EDIT_META_KEY, "0")
        _with_project(lib, safe, setup)
        assert _verdict(lib, safe).verdict == AUTO_EDIT_OFF
    finally:
        lib.close()


def test_the_job_finishes_only_the_unedited_and_names_the_rest(built_library, monkeypatch):
    from webapp.routers.editor import RECIPE_META_PREFIX

    calls: list[tuple] = []

    def _fake(lib, safe, run_id, auto_crop=True):  # noqa: ANN001
        calls.append((safe, run_id, auto_crop))
        return 3

    monkeypatch.setattr("webapp.pipeline._auto_edit_process_run", _fake)
    lib = Library.open_or_create(built_library / "library")
    try:
        a, b = (t.safe_name for t in lib.list_targets()[:2])
        shown = _with_project(lib, a, lambda p: _run(p, "2026-09-10T00:00:00Z"))

        def edited(p):
            rid = _run(p, "2026-09-10T00:00:00Z")
            p.set_meta(f"{RECIPE_META_PREFIX}{rid}", json.dumps({"ops": _OPS}))
        _with_project(lib, b, edited)
        b_name = lib.find_target(b).name
    finally:
        lib.close()

    summary = _run_body(pipeline.submit_finish_unedited_pictures, _settings(built_library),
                        Job(kind="finish_unedited_pictures"))
    assert calls == [(a, shown, True)]
    assert len(summary["finished"]) == 1
    assert summary["left_alone"] == {HAS_EDIT: [b_name]}
    assert summary["failed"] == [] and summary["cancelled"] is False


def test_the_job_really_finishes_a_ragged_mosaic_picture(built_library):
    """End to end through the real writer: the never-edited run gets Auto's
    recipe, a baked preview, and — the owner's complaint — a trimmed border."""
    from PIL import Image

    from seestack.previewcrop import parse_preview_crop
    from webapp.finishedpicture import run_is_a_finished_picture
    from webapp.routers.editor import RECIPE_META_PREFIX

    from .test_adjust_keeps_processed import _H, _W, _register_run

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
    finally:
        lib.close()
    run_id, preview = _register_run(built_library, safe, trimmable=True)

    summary = _run_body(pipeline.submit_finish_unedited_pictures, _settings(built_library),
                        Job(kind="finish_unedited_pictures"))
    assert summary["failed"] == []
    assert lib_name(built_library, safe) in summary["finished"]

    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.get_meta(f"{RECIPE_META_PREFIX}{run_id}")
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
            assert run_is_a_finished_picture(proj, run)
            crop = parse_preview_crop(run.preview_crop_json)
        finally:
            proj.close()
    finally:
        lib.close()
    with Image.open(preview) as im:
        assert im.size[0] < _W and im.size[1] < _H   # the ragged border is gone
    assert crop is not None and crop.w_frac < 1.0
    # Run again: nothing is unedited any more, so nothing is touched.
    again = _run_body(pipeline.submit_finish_unedited_pictures, _settings(built_library),
                      Job(kind="finish_unedited_pictures"))
    assert lib_name(built_library, safe) not in again["finished"]


def lib_name(root, safe: str) -> str:
    lib = Library.open_or_create(root / "library")
    try:
        return lib.find_target(safe).name
    finally:
        lib.close()


def test_preview_endpoint_names_both_groups_and_writes_nothing(built_library, client):
    from webapp.routers.editor import RECIPE_META_PREFIX

    lib = Library.open_or_create(built_library / "library")
    try:
        safe = _first_target(lib)
        shown = _with_project(lib, safe, lambda p: _run(p, "2026-09-10T00:00:00Z"))
    finally:
        lib.close()
    r = client.get("/api/unstretched-pictures/finish-unedited")
    assert r.status_code == 200
    body = r.json()
    assert safe in [t["safe_name"] for t in body["finish"]]
    assert isinstance(body["left_alone"], dict)
    lib = Library.open_or_create(built_library / "library")
    try:
        assert _with_project(
            lib, safe, lambda p: p.get_meta(f"{RECIPE_META_PREFIX}{shown}")) is None
    finally:
        lib.close()


def test_start_endpoint_queues_one_job(client):
    r1 = client.post("/api/unstretched-pictures/finish-unedited")
    assert r1.status_code == 200 and r1.json()["job_id"]
