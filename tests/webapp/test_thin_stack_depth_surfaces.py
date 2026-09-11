"""The thin-stack cue is a claim about a *pixel*, on every surface that makes it.

``thinStackWarning`` exists for the owner's "gibberish" case: a picture only a
sub or two deep comes out as per-pixel colour speckle, so the app says so rather
than presenting it as a finished result. v0.419.1 made that reading per-pixel on
the **Target page**, from the run's own ``field_fulls`` — nine subs over a 3x3
raster is one sub everywhere, and the target's frame count cannot say so.

Its three other surfaces were left reading the count: the Dashboard's recent
strip and the Gallery grid (both through ``FrameCountBadge``) and the Jobs page's
"Process target" summary — which is the walk-away path, i.e. the one the owner
actually meets a thin mosaic on. Neither listing carried the figure at all, and
neither did the stack job's result, so the fix is one additive field on each.

These tests pin what the three endpoints serve; ``FrameCountBadge.test.tsx``,
``Gallery.test.tsx``, ``Dashboard.test.tsx`` and ``Jobs.test.tsx`` pin what the
surfaces do with it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from seestack.io.library import Library
from seestack.io.project import StackRunRow

# Match the ``solved_library`` fixture's seeded frames (tests/webapp/conftest.py).
FRAME_W, FRAME_H = 480, 320


def _add_run(
    data_root: Path,
    safe: str,
    *,
    canvas_w: int,
    canvas_h: int,
    n_frames_used: int = 9,
    drizzle: bool = False,
    drizzle_scale: float = 1.0,
) -> int:
    """Attach one stack run of the given canvas to a fixture target."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None,
                timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master",
                fits_path=None, tiff_path=None, preview_path=None,
                n_frames_used=n_frames_used,
                canvas_h=canvas_h, canvas_w=canvas_w,
                coverage_min=1, coverage_max=n_frames_used,
                total_exposure_s=None,
                options_json=json.dumps({
                    "drizzle": drizzle, "drizzle_scale": drizzle_scale,
                }),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _gallery(client) -> list[dict]:
    resp = client.get("/api/gallery")
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _recent(client) -> list[dict]:
    resp = client.get("/api/stats")
    assert resp.status_code == 200, resp.text
    return resp.json()["recent_stacks"]


# --------------------------------------------------------------------------
# The Gallery grid


def test_the_gallery_reports_a_mosaic_runs_depth_scale(client, solved_library):
    """Nine subs over a 3x3 raster: the badge needs the 9.0, not the 9."""
    _add_run(solved_library, "M_42", canvas_w=FRAME_W * 3, canvas_h=FRAME_H * 3)

    assert [it["field_fulls"] for it in _gallery(client)] == [9.0]


def test_the_gallery_reports_one_field_full_for_a_single_field(
    client, solved_library,
):
    """The no-op case that guarantees a single-field owner is unaffected: the
    scale is 1.0, so the cue reads exactly the count it always read."""
    _add_run(solved_library, "M_42", canvas_w=FRAME_W, canvas_h=FRAME_H)

    assert [it["field_fulls"] for it in _gallery(client)] == [1.0]


def test_the_gallery_divides_out_drizzle_super_sampling(client, solved_library):
    """A 2x drizzled single field has 4x the pixels and still covers one field of
    sky — the same division the run listing already does, from the same helper."""
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
        drizzle=True, drizzle_scale=2.0,
    )

    assert [it["field_fulls"] for it in _gallery(client)] == [1.0]


def test_the_gallery_field_is_present_but_null_without_a_native_frame_shape(
    client, solved_library, monkeypatch,
):
    """An older library whose frames never recorded ``width_px`` has nothing to
    compare a canvas against. Present and ``None`` — which every reader treats as
    1.0, i.e. exactly the behaviour before the field existed."""
    import webapp.routers.gallery as gallery_router

    monkeypatch.setattr(gallery_router, "native_frame_shape", lambda _proj: None)
    _add_run(solved_library, "M_42", canvas_w=FRAME_W * 3, canvas_h=FRAME_H * 3)

    items = _gallery(client)
    assert items and all("field_fulls" in it for it in items)
    assert [it["field_fulls"] for it in items] == [None]


# --------------------------------------------------------------------------
# The Dashboard's recent-stacks strip


def test_the_dashboard_strip_reports_a_mosaic_runs_depth_scale(
    client, solved_library,
):
    _add_run(solved_library, "M_42", canvas_w=FRAME_W * 3, canvas_h=FRAME_H * 3)

    assert [s["field_fulls"] for s in _recent(client)] == [9.0]


def test_the_dashboard_strip_reports_one_field_full_for_a_single_field(
    client, solved_library,
):
    _add_run(solved_library, "M_42", canvas_w=FRAME_W, canvas_h=FRAME_H)

    assert [s["field_fulls"] for s in _recent(client)] == [1.0]


def test_the_two_listings_agree_about_one_run(client, solved_library):
    """The point of taking both from one helper: the Gallery card and the
    Dashboard tile show the same picture and must not disagree about it."""
    _add_run(solved_library, "M_42", canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 3)

    assert [it["field_fulls"] for it in _gallery(client)] == \
        [s["field_fulls"] for s in _recent(client)]


# --------------------------------------------------------------------------
# The stack job's own result — the walk-away path


def _fake_stack(monkeypatch, *, canvas_shape: tuple[int, int, int]):
    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=9,
            canvas_shape=canvas_shape,
            cancelled=False, errors=[], excluded_frames=[],
            n_offered=9, n_align_failed=0,
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)


def _run_stack_job(data_root: Path, *, drizzle: bool = False) -> dict:
    from webapp import pipeline
    from webapp.jobs import Job

    from .test_auto_stack_pipeline import _FakeJM, _first_stackable, _settings

    lib = Library.open_or_create(data_root / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        options = {"drizzle": True, "drizzle_scale": 2.0} if drizzle else None
        return pipeline._stack_target(
            _settings(data_root), _FakeJM(), Job(kind="stack"), lib, safe,
            options=options,
        )
    finally:
        lib.close()


def test_the_stack_job_result_carries_its_canvas_depth_scale(
    solved_library, monkeypatch,
):
    """The walk-away case the Jobs page reports: a 3x3-canvas stack of nine subs
    is one sub deep everywhere, and the result must say so, or the summary reads
    "Stacked 9 frames" with no heads-up at all."""
    _fake_stack(monkeypatch, canvas_shape=(FRAME_H * 3, FRAME_W * 3, 3))

    assert _run_stack_job(solved_library)["field_fulls"] == 9.0


def test_the_stack_job_result_reports_one_field_full_for_a_single_field(
    solved_library, monkeypatch,
):
    _fake_stack(monkeypatch, canvas_shape=(FRAME_H, FRAME_W, 3))

    assert _run_stack_job(solved_library)["field_fulls"] == 1.0


def test_the_stack_job_result_divides_out_drizzle(solved_library, monkeypatch):
    """The options the job *ran* are a dict, not stored JSON — so this is the one
    caller reading the drizzle scale through ``drizzle_scale_of``. A 2x drizzled
    single field is still one field of sky."""
    _fake_stack(monkeypatch, canvas_shape=(FRAME_H * 2, FRAME_W * 2, 3))

    assert _run_stack_job(solved_library, drizzle=True)["field_fulls"] == 1.0
