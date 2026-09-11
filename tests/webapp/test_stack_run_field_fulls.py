"""Every stack run says how much *sky* its own canvas covers.

A mosaic's canvas grows as its panels are shot, so two runs of one target can
span very different areas. ``total_exposure_s`` alone therefore cannot say
whether a target got **deeper** or merely **wider** between two runs — and the
noise-vs-time trend on the Target and History pages (``integrationTrend``) fits
its falloff exponent across exactly that pair. Read off the totals, a 2x2 mosaic
that grew to a 3x3 at the same per-panel depth has 2.25x the light and identical
grain, which reads as *"your noise stopped dropping as you added time"* — the
sky-limited plateau verdict, telling the owner to move on from a mosaic that is
only a few subs deep everywhere.

The fix ships the same ``field_fulls`` figure the readiness verdict already uses
(``webapp.field_fulls``), but **per run** rather than for the target's newest,
so the trend divides each run's total by its own canvas. These tests pin what
the listing serves; ``integrationTrend.test.ts`` pins what the verdict does
with it.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    timestamp_utc: str = "2026-05-01T00:00:00Z",
    n_frames_used: int = 200,
    total_exposure_s: float | None = None,
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
                timestamp_utc=timestamp_utc,
                output_basename="master",
                fits_path=None, tiff_path=None, preview_path=None,
                n_frames_used=n_frames_used,
                canvas_h=canvas_h, canvas_w=canvas_w,
                coverage_min=1, coverage_max=n_frames_used,
                total_exposure_s=total_exposure_s,
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


def _runs(client, safe: str) -> list[dict]:
    resp = client.get(f"/api/targets/{safe}/stack-runs")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_a_single_field_run_reports_one_field_full(client, solved_library):
    """The no-op case, and the one that guarantees the fix changes nothing for
    a single-field owner: canvas == one native frame, so the scale divides out
    of every ratio the trend takes."""
    _add_run(solved_library, "M_42", canvas_w=FRAME_W, canvas_h=FRAME_H)

    assert [r["field_fulls"] for r in _runs(client, "M_42")] == [1.0]


def test_a_2x2_mosaic_run_reports_four(client, solved_library):
    """The canonical mosaic shape — four field-fulls of sky, so one pixel of it
    received a quarter of the run's total light."""
    _add_run(solved_library, "M_42", canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2)

    assert [r["field_fulls"] for r in _runs(client, "M_42")] == [4.0]


def test_each_run_reports_its_own_canvas_not_the_newest(client, solved_library):
    """The whole point: a growing mosaic's two runs must not share one figure.

    2x2 at 0.5 h a panel, then 3x3 at 0.5 h a panel — 2 h of total light, then
    4.5 h, for the *same* depth everywhere. With a per-run figure the trend can
    see that 2/4 == 4.5/9 and decline to claim a plateau; with the target-level
    number both runs would divide by 9 and the false plateau would survive.
    """
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
        timestamp_utc="2026-05-01T00:00:00Z", total_exposure_s=2 * 3600.0,
    )
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 3, canvas_h=FRAME_H * 3,
        timestamp_utc="2026-05-08T00:00:00Z", total_exposure_s=4.5 * 3600.0,
    )

    by_canvas = {
        r["canvas_w"]: (r["field_fulls"], r["total_exposure_s"])
        for r in _runs(client, "M_42")
    }
    assert by_canvas[FRAME_W * 2] == (4.0, 2 * 3600.0)
    assert by_canvas[FRAME_W * 3] == (9.0, 4.5 * 3600.0)
    # …and the per-pixel integration the trend fits against is identical, which
    # is the fact the totals hide.
    assert (2 * 3600.0) / 4.0 == (4.5 * 3600.0) / 9.0


def test_drizzle_super_sampling_is_divided_out(client, solved_library):
    """A 2x drizzled single field has 4x the *pixels* and still covers one field
    of sky. Without this the trend would divide a drizzled single-field target's
    integration by four — harmless to the ratio (every run shares it), but the
    figure would be a lie the next reader builds on."""
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
        drizzle=True, drizzle_scale=2.0,
    )

    assert [r["field_fulls"] for r in _runs(client, "M_42")] == [1.0]


def test_the_field_is_present_but_null_when_no_frame_records_its_shape(
    client, solved_library, monkeypatch,
):
    """An older library whose frames never recorded ``width_px`` has no native
    field to compare a canvas against. The field must still be *present* (an
    older frontend reads it as absent either way) and ``None``, which every
    reader treats as 1.0 — i.e. exactly the pre-field behaviour."""
    import webapp.routers.stack as stack_router

    monkeypatch.setattr(stack_router, "native_frame_shape", lambda _proj: None)
    _add_run(solved_library, "M_42", canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2)

    rows = _runs(client, "M_42")
    assert rows and all("field_fulls" in r for r in rows)
    assert [r["field_fulls"] for r in rows] == [None]
