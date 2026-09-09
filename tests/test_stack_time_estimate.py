"""How long will this stack take? — the measured answer, and its refusals.

The app could say how much longer a *running* stack had to go and nothing at all
before the button, which is where the decision actually is ("start it now, or in
the morning?"). :mod:`seestack.stacktime` answers it by measuring rather than
modelling: every finished run now records its own wall clock, and the estimate is
the median seconds-per-sub of this target's own **comparable** runs.

Most of what is worth testing here is what it *refuses* to answer, because a
wrong number costs more trust than no number.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from seestack.io.project import SCHEMA_VERSION, Project, StackRunRow
from seestack.stacktime import (
    MAX_BASIS_RUNS,
    MAX_CANVAS_RATIO,
    MIN_BASIS_FRAMES,
    PastStack,
    estimate_from_runs,
    estimate_stack_seconds,
    past_stack,
    stack_cost_class,
)

_CANVAS = 480 * 320


def _run(n_frames: int, duration_s: float, *, canvas_px: int = _CANVAS,
         cost_class: str = "sigma-clip") -> PastStack:
    return PastStack(n_frames=n_frames, duration_s=duration_s,
                     canvas_px=canvas_px, cost_class=cost_class)


def _row(**kw) -> StackRunRow:
    """A ``stack_runs`` row with the fields the estimate reads, defaulted to a
    perfectly ordinary timed κ-σ run."""
    fields = {
        "id": 1,
        "timestamp_utc": "2026-05-01T00:00:00Z",
        "output_basename": "master",
        "fits_path": None, "tiff_path": None, "preview_path": None,
        "n_frames_used": 100,
        "canvas_h": 320, "canvas_w": 480,
        "coverage_min": 1, "coverage_max": 100,
        "options_json": json.dumps({"sigma_clip": True}),
        "duration_s": 200.0,
    }
    fields.update(kw)
    return StackRunRow(**fields)


# --- the rate, and what counts as evidence for it ----------------------------


def test_the_estimate_is_the_median_rate_of_the_target_s_own_runs():
    """Two comparable runs at 2.0 and 2.4 s a sub → 2.2 s a sub × 500 subs."""
    est = estimate_stack_seconds(
        [_run(100, 200.0), _run(50, 120.0)],
        n_frames=500, canvas_px=_CANVAS, cost_class="sigma-clip")
    assert est is not None
    assert est.per_frame_s == pytest.approx(2.2)
    assert est.seconds == pytest.approx(1100.0)
    assert est.basis_runs == 2
    assert est.basis_frames == 100


def test_one_past_run_is_enough_to_answer_with():
    """The value is highest on the *second* stack of a target, so a single timed
    run counts — the wording is what carries the caveat, not silence."""
    est = estimate_stack_seconds([_run(40, 80.0)], n_frames=40,
                                 canvas_px=_CANVAS, cost_class="sigma-clip")
    assert est is not None and est.basis_runs == 1
    assert est.seconds == pytest.approx(80.0)


def test_only_the_newest_handful_of_runs_are_averaged():
    """A long History must not drag a rate measured on old data (or old
    hardware) into today's answer: only the first MAX_BASIS_RUNS matches count,
    and the caller passes them newest-first."""
    newest = [_run(100, 100.0) for _ in range(MAX_BASIS_RUNS)]
    ancient = [_run(100, 1000.0) for _ in range(20)]
    est = estimate_stack_seconds(newest + ancient, n_frames=100,
                                 canvas_px=_CANVAS, cost_class="sigma-clip")
    assert est is not None
    assert est.basis_runs == MAX_BASIS_RUNS
    assert est.seconds == pytest.approx(100.0)


# --- the refusals ------------------------------------------------------------


def test_a_run_of_different_settings_is_not_evidence():
    """A drizzle run does several times the per-sub work of a plain κ-σ one. No
    scaling factor between the classes is offered anywhere, on purpose."""
    assert estimate_stack_seconds([_run(100, 200.0, cost_class="drizzle")],
                                  n_frames=100, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is None


def test_a_run_too_small_to_generalise_from_is_not_evidence():
    """Below the floor a run is mostly start-up cost, so its seconds-per-sub
    describes the setup, not the stack."""
    tiny = _run(MIN_BASIS_FRAMES - 1, 60.0)
    assert estimate_stack_seconds([tiny], n_frames=500, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is None
    # …and one sub over the floor is.
    ok = _run(MIN_BASIS_FRAMES, 60.0)
    assert estimate_stack_seconds([ok], n_frames=500, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is not None


def test_a_wildly_different_canvas_is_not_evidence():
    """The same subs cost more reprojected onto a mosaic's union canvas than
    onto one reference frame, so a much bigger canvas is a different job."""
    far = _run(100, 200.0, canvas_px=int(_CANVAS * MAX_CANVAS_RATIO * 1.5))
    assert estimate_stack_seconds([far], n_frames=100, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is None
    near = _run(100, 200.0, canvas_px=int(_CANVAS * 1.5))
    assert estimate_stack_seconds([near], n_frames=100, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is not None
    # …and the window is symmetric: a much *smaller* canvas is no better.
    small = _run(100, 200.0, canvas_px=int(_CANVAS / (MAX_CANVAS_RATIO * 1.5)))
    assert estimate_stack_seconds([small], n_frames=100, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is None


def test_no_history_at_all_answers_nothing():
    assert estimate_stack_seconds([], n_frames=100, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is None


# --- reading rows: only a *timed stack* is evidence ---------------------------


def test_a_run_recorded_before_runs_were_timed_is_skipped():
    """Every run in the owner's existing library has a NULL duration. They must
    read as "no evidence", never as an instant stack."""
    assert past_stack(_row(duration_s=None)) is None


def test_a_row_that_is_not_a_stack_is_skipped():
    """An editor export and a channel combine write ``stack_runs`` rows too and
    neither is a stack — the stacker is the only writer that times itself, so
    both leave the column NULL and are skipped by the same rule."""
    assert past_stack(_row(duration_s=None, notes="edited")) is None


@pytest.mark.parametrize("bad", [
    {"duration_s": 0.0},
    {"duration_s": -5.0},
    {"n_frames_used": 0},
    {"canvas_w": 0},
    {"options_json": "not json"},
    {"options_json": json.dumps([1, 2, 3])},
])
def test_an_unusable_row_costs_a_data_point_never_an_exception(bad):
    assert past_stack(_row(**bad)) is None


def test_estimate_from_runs_reads_rows_and_ignores_the_unusable_ones():
    rows = [
        _row(duration_s=None),                       # pre-upgrade run
        _row(n_frames_used=100, duration_s=200.0),   # evidence
        _row(options_json="{{{"),                    # corrupt
    ]
    est = estimate_from_runs(rows, n_frames=100, canvas_px=_CANVAS,
                             cost_class="sigma-clip")
    assert est is not None and est.basis_runs == 1
    assert est.seconds == pytest.approx(200.0)


# --- the cost class is the engine's own combine answer -----------------------


@pytest.mark.parametrize("options,expected", [
    ({"sigma_clip": True}, "sigma-clip"),
    ({"sigma_clip": False}, "mean"),
    ({"min_max_reject": True, "sigma_clip": True}, "min-max-reject"),
    ({"drizzle": True}, "drizzle"),
    ({"drizzle": True, "drizzle_reject": True}, "drizzle+reject"),
])
def test_the_cost_class_names_the_combine_that_will_run(options, expected):
    assert stack_cost_class(options, 100) == expected


def test_the_cost_class_is_combine_method_plus_the_drizzle_reject_split():
    """Not a copy of the dispatcher's rules — the same function, so a change to
    the gates cannot leave two different answers in the app. Includes the silent
    fall-throughs: a 3-frame κ-σ run really does combine as a plain mean."""
    from seestack.stack.stacker import StackOptions, combine_method

    for opts in (
        StackOptions(sigma_clip=True),
        StackOptions(sigma_clip=False),
        StackOptions(min_max_reject=True),
        StackOptions(drizzle=True),
    ):
        for n in (2, 3, 4, 100):
            mapping = {"drizzle": opts.drizzle, "drizzle_reject": opts.drizzle_reject,
                       "min_max_reject": opts.min_max_reject,
                       "sigma_clip": opts.sigma_clip}
            assert stack_cost_class(mapping, n) == combine_method(opts, n)


# --- the column: it is written, and an old project gains it ------------------


def test_a_stack_records_how_long_it_took(tmp_path):
    """The whole feature rests on this row: without a duration there is nothing
    to measure the next run against. Fails before v0.399.0 — the column, and the
    field, did not exist."""
    pytest.importorskip("astropy")
    pytest.importorskip("photutils")
    pytest.importorskip("scipy")
    from seestack.io.project import FrameRow
    from seestack.stack.stacker import StackOptions, run_stack
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    proj = Project.create(tmp_path / "p", name="timed")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(3):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True, seed=i,
                                  n_stars=20)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    try:
        run_stack(proj, StackOptions(sigma_clip=False, background_flatten=False,
                                     max_workers=2, output_name="timed"))
        rows = list(proj.iter_stack_runs())
    finally:
        proj.close()
    assert len(rows) == 1
    assert rows[0].duration_s is not None
    assert rows[0].duration_s > 0.0
    # …and it is the run's own wall clock, not a stamp of something else: a
    # three-frame synthetic stack is quick, but it is not instant either.
    assert rows[0].duration_s < 600.0


def test_an_older_project_gains_the_duration_on_open_without_a_version_bump(tmp_path):
    """Upgrade safety (§9), and specifically **rollback** safety: the column is
    additive through ``_reconcile_table_columns``, not through a
    ``SCHEMA_VERSION`` bump — an older build refuses to open a project stamped
    newer than itself, so bumping would mean this feature could not be rolled
    back. A project missing the column must gain it on open and keep every row.

    (Written this way because the first version of this change *did* bump the
    version, and `test_uncovered_fraction.py`'s rollback guard failed —
    a red test that was information about the design, not an obstacle to it.)"""
    proj_dir = tmp_path / "t"
    proj = Project.create(proj_dir, name="T")
    try:
        proj.add_stack_run(_row(id=None, duration_s=None, output_basename="old"))
    finally:
        proj.close()

    db = proj_dir / "project.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.execute("ALTER TABLE stack_runs DROP COLUMN duration_s")
        conn.commit()
        version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    proj = Project.open(proj_dir)
    try:
        runs = list(proj.iter_stack_runs())
        assert [r.output_basename for r in runs] == ["old"]
        # NULL reads as "this one was never timed", so the estimate self-hides on
        # an upgraded library rather than inventing a rate.
        assert runs[0].duration_s is None
        assert estimate_from_runs(runs, n_frames=100, canvas_px=_CANVAS,
                                  cost_class="sigma-clip") is None
        # …and the reconciled DB records it on the next stack.
        proj.add_stack_run(_row(id=None, output_basename="new", duration_s=200.0))
        fresh = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert fresh["new"].duration_s == pytest.approx(200.0)
        assert fresh["old"].duration_s is None
    finally:
        proj.close()

    # The version is untouched, which is what keeps a rollback openable.
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version_before
        assert version_before == SCHEMA_VERSION
    finally:
        conn.close()


def test_an_old_build_can_still_read_a_project_this_build_wrote(tmp_path):
    """The other direction of "additive": a build that has never heard of
    ``duration_s`` must still open a DB this one wrote and read its runs — the
    check a bumped ``SCHEMA_VERSION`` would have failed."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(id=None, output_basename="new", duration_s=200.0))
    finally:
        proj.close()

    conn = sqlite3.connect(tmp_path / "t" / "project.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] <= 22
        row = conn.execute(
            "SELECT output_basename, n_frames_used FROM stack_runs").fetchone()
        assert row["output_basename"] == "new"
    finally:
        conn.close()
