"""Healing an older run's thin-coverage share from the map it already wrote.

``stack_runs.coverage_thin_frac`` arrived with schema 20, so every run the owner
already has reads NULL — and "How's my stack?" says nothing at all about
coverage on a NULL, by design. The number is a pure function of the coverage
sibling those runs wrote anyway, so it can be recovered rather than waited for.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from seestack.coverage_backfill import backfill_coverage_thin_frac
from seestack.io.project import Project, StackRunRow
from seestack.stack.stacker import coverage_thin_fraction


def _run(**kw) -> StackRunRow:
    base = dict(
        id=None, timestamp_utc="2026-08-31T00:00:00+00:00", output_basename="m42",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=30,
        canvas_h=300, canvas_w=300, coverage_min=1, coverage_max=12,
        options_json="{}", coverage_thin_frac=None,
    )
    base.update(kw)
    return StackRunRow(**base)


def _ragged_border_coverage() -> np.ndarray:
    """A well-covered picture with a genuinely ragged edge: twelve frames deep
    everywhere except a 20-px band down one side that got one — the shape the
    note exists to catch, and one a "Trim border" actually fixes.
    ``coverage_thin_fraction`` reads 1/15.

    What this fixture can vouch for: a *border*, i.e. a thin region small enough
    (6.7 % of the covered area, under ``PANEL_LEVEL_MIN_FRAC``) that it is not a
    coverage plateau of its own. It is deliberately **not** a lopsided two-panel
    mosaic — it was one until v0.389.2, ⅔ of the canvas at one frame and ⅓ at
    twelve, which is a *panel* that got a bad night rather than an edge, reads
    ⅔ "thin" only against the peak, and is kept whole by the very trim the note
    offers. Panel-shaped coverage belongs in ``tests/test_coverage_thin.py``.
    """
    cov = np.full((300, 300), 12.0, dtype=np.float32)
    cov[:, :20] = 1.0
    return cov


def _write_map(path: Path, cov: np.ndarray) -> None:
    from astropy.io import fits

    path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=np.asarray(cov, dtype=np.float32)).writeto(
        path, overwrite=True)


def _project_with_run(tmp_path: Path, run: StackRunRow) -> tuple[Project, int]:
    proj = Project.create(tmp_path / "t", name="T")
    run_id = proj.add_stack_run(run)
    return proj, run_id


def test_an_old_run_gets_its_share_back_from_its_frame_count_map(tmp_path):
    """The heal itself: a NULL row plus the sibling on disk answers exactly what
    a fresh stack of the same data would have stamped."""
    fits_path = tmp_path / "out" / "m42.fits"
    cov = _ragged_border_coverage()
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert row.coverage_thin_frac is None  # what the owner's library looks like

        share = backfill_coverage_thin_frac(proj, row)
        assert share == pytest.approx(coverage_thin_fraction(cov))
        assert share == pytest.approx(1 / 15, abs=0.01)
        # The caller's copy grades like a freshly-stacked run…
        assert row.coverage_thin_frac == pytest.approx(share)
        # …and so does every later read, without touching the map again.
        again = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert again.coverage_thin_frac == pytest.approx(share)
    finally:
        proj.close()


def test_it_prefers_the_frame_count_sibling_over_the_weighted_map(tmp_path):
    """The same preference ``run_stack`` makes when it stamps the column: the
    weighted map is Σ of per-frame *weights*, so binning it describes how good
    the subs were as much as how many there were."""
    fits_path = tmp_path / "out" / "m42.fits"
    frames = _ragged_border_coverage()
    _write_map(fits_path.with_name("m42_framecov.fits"), frames)
    # A weighted map of the same canvas that would read as perfectly even.
    _write_map(fits_path.with_name("m42_coverage.fits"),
               np.full((300, 300), 9.0, dtype=np.float32))

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_thin_frac(proj, row) == pytest.approx(
            coverage_thin_fraction(frames))
    finally:
        proj.close()


def test_the_weighted_map_is_the_fallback_when_there_is_no_frame_count(tmp_path):
    """Runs old enough to predate the frame-count sibling still have the
    weighted one, and the min/max path's map *is* a true count."""
    fits_path = tmp_path / "out" / "m42.fits"
    cov = _ragged_border_coverage()
    _write_map(fits_path.with_name("m42_coverage.fits"), cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_thin_frac(proj, row) == pytest.approx(
            coverage_thin_fraction(cov))
    finally:
        proj.close()


def test_no_map_on_disk_stays_silent_rather_than_guessing(tmp_path):
    """Care point 3: a missing sibling leaves the row NULL. It must never fall
    back to the ``coverage_min`` test this column replaced — that test fired on
    every stack the app has ever made."""
    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(tmp_path / "out" / "gone.fits")))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_thin_frac(proj, row) is None
        assert row.coverage_thin_frac is None
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).coverage_thin_frac is None
    finally:
        proj.close()


def test_a_run_with_no_master_path_is_not_an_error(tmp_path):
    proj, run_id = _project_with_run(tmp_path, _run(fits_path=None))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_thin_frac(proj, row) is None
    finally:
        proj.close()


def test_an_empty_map_is_no_answer_rather_than_zero(tmp_path):
    """A canvas with nothing covered can't say "no thin border" — and writing 0
    would earn the run an "even coverage" compliment it has not earned."""
    fits_path = tmp_path / "out" / "m42.fits"
    _write_map(fits_path.with_name("m42_framecov.fits"),
               np.zeros((50, 50), dtype=np.float32))

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_thin_frac(proj, row) is None
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).coverage_thin_frac is None
    finally:
        proj.close()


def test_a_run_that_already_has_both_shares_is_left_exactly_alone(tmp_path,
                                                                 monkeypatch):
    """The common case — every run stacked since both columns existed *and*
    stamped with the current measuring rule — must cost nothing: no map read, no
    write, and certainly no re-measurement."""
    from seestack.stack.stacker import COVERAGE_SHARES_VERSION

    fits_path = tmp_path / "out" / "m42.fits"
    # A map that would measure 1/15 if it were ever read.
    _write_map(fits_path.with_name("m42_framecov.fits"), _ragged_border_coverage())

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), coverage_thin_frac=0.004,
                       uncovered_frac=0.02, coverage_median_depth=12.0,
                       coverage_shares_version=COVERAGE_SHARES_VERSION))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)

        def _no_read(*_a, **_k):  # pragma: no cover - the point is it isn't hit
            raise AssertionError("a complete run must not open its coverage map")

        monkeypatch.setattr("seestack.edit.proxy.load_frame_coverage", _no_read)
        monkeypatch.setattr("seestack.edit.proxy.load_coverage", _no_read)
        assert backfill_coverage_thin_frac(proj, row) == pytest.approx(0.004)
        assert row.coverage_thin_frac == pytest.approx(0.004)
        assert row.uncovered_frac == pytest.approx(0.02)
    finally:
        proj.close()


# --- the empty-canvas share heals off the same read --------------------------


def test_the_two_shares_are_healed_together_from_one_read(tmp_path):
    """A run predating either column pays exactly one map read for both — and a
    mosaic's empty corners are precisely what the thin share cannot report."""
    from seestack.coverage_backfill import backfill_coverage_shares
    from seestack.stack.stacker import uncovered_fraction

    fits_path = tmp_path / "out" / "m42.fits"
    cov = np.full((200, 200), 12.0, dtype=np.float32)
    cov[:100, :100] = 0.0            # a quarter of the canvas: no frame reached
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    reads = {"n": 0}

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert row.uncovered_frac is None

        import seestack.edit.proxy as proxy

        real = proxy.load_frame_coverage

        def _counted(*a, **k):
            reads["n"] += 1
            return real(*a, **k)

        proxy.load_frame_coverage = _counted  # type: ignore[assignment]
        try:
            backfill_coverage_shares(proj, row)
        finally:
            proxy.load_frame_coverage = real  # type: ignore[assignment]

        assert reads["n"] == 1
        assert row.uncovered_frac == pytest.approx(uncovered_fraction(cov))
        assert row.uncovered_frac == pytest.approx(0.25)
        assert row.coverage_thin_frac == pytest.approx(coverage_thin_fraction(cov))
        # …and both are remembered, so the next read of the row is free.
        again = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert again.uncovered_frac == pytest.approx(0.25)
        assert again.coverage_thin_frac == pytest.approx(
            coverage_thin_fraction(cov))
    finally:
        proj.close()


def test_healing_only_the_missing_half_leaves_the_other_untouched(tmp_path):
    """A run stacked between the two columns carries a thin share already; the
    heal must fill in the empty share without re-measuring — or overwriting —
    the number the stacker itself stamped **under the current rule**."""
    from seestack.coverage_backfill import backfill_coverage_shares
    from seestack.stack.stacker import COVERAGE_SHARES_VERSION

    fits_path = tmp_path / "out" / "m42.fits"
    cov = np.full((100, 100), 8.0, dtype=np.float32)
    cov[:, :30] = 0.0
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), coverage_thin_frac=0.123,
                       coverage_shares_version=COVERAGE_SHARES_VERSION))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        backfill_coverage_shares(proj, row)
        assert row.coverage_thin_frac == pytest.approx(0.123)
        assert row.uncovered_frac == pytest.approx(0.3)
    finally:
        proj.close()


# --- re-deriving a share an older rule measured ------------------------------
#
# Until v0.389.2 the thin share was measured against the coverage map's *peak*,
# which on a mosaic is where panels overlap — so the owner's existing mosaics
# carry a stamped number saying most of the picture is a ragged border. They must
# heal off the map they already wrote, not wait to be stacked again.


def test_a_mosaic_stamped_under_the_old_rule_is_re_derived(tmp_path):
    """Fails before: the row's peak-referenced ⅔ survived untouched, because the
    heal only ever filled in a NULL."""
    from seestack.coverage_backfill import backfill_coverage_shares
    from seestack.stack.stacker import COVERAGE_SHARES_VERSION

    fits_path = tmp_path / "out" / "m42.fits"
    # A lopsided two-panel mosaic: ⅔ of the canvas one frame deep, ⅓ twelve.
    cov = np.ones((300, 300), dtype=np.float32)
    cov[:, 200:] = 12.0
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), is_mosaic=True,
                       coverage_thin_frac=2 / 3, uncovered_frac=0.0))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert row.coverage_shares_version is None      # the owner's library
        backfill_coverage_shares(proj, row)

        assert row.coverage_thin_frac == pytest.approx(coverage_thin_fraction(cov))
        assert row.coverage_thin_frac < 0.02
        assert row.coverage_shares_version == COVERAGE_SHARES_VERSION
        # …and it is remembered, so the next read costs nothing.
        again = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert again.coverage_thin_frac < 0.02
        assert again.coverage_shares_version == COVERAGE_SHARES_VERSION
    finally:
        proj.close()


def test_a_single_field_stamped_under_the_old_rule_never_reopens_its_map(
        tmp_path, monkeypatch):
    """The rule that changed is the *reference*, and on a single field the old
    peak and the new panel depth are the same number — so its stored share is
    right to the digit and re-reading the map would buy nothing."""
    from seestack.coverage_backfill import backfill_coverage_shares

    fits_path = tmp_path / "out" / "m42.fits"
    _write_map(fits_path.with_name("m42_framecov.fits"), _ragged_border_coverage())

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), is_mosaic=False,
                       coverage_thin_frac=0.0667, uncovered_frac=0.0,
                       coverage_median_depth=12.0))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)

        def _no_read(*_a, **_k):  # pragma: no cover - the point is it isn't hit
            raise AssertionError("a single field's share was already correct")

        monkeypatch.setattr("seestack.edit.proxy.load_frame_coverage", _no_read)
        monkeypatch.setattr("seestack.edit.proxy.load_coverage", _no_read)
        backfill_coverage_shares(proj, row)
        assert row.coverage_thin_frac == pytest.approx(0.0667)
    finally:
        proj.close()


def test_a_stale_mosaic_whose_map_is_gone_goes_quiet_without_losing_the_row(
        tmp_path):
    """It cannot be re-measured, and repeating a number known to be measured the
    wrong way is worse than saying nothing — but the row keeps what it has, so
    the run heals for real if the map ever comes back."""
    from seestack.coverage_backfill import backfill_coverage_shares

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(tmp_path / "out" / "gone.fits"),
                       is_mosaic=True, coverage_thin_frac=2 / 3))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        backfill_coverage_shares(proj, row)
        assert row.coverage_thin_frac is None            # the caller stays silent
        stored = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert stored.coverage_thin_frac == pytest.approx(2 / 3)   # never deleted
        assert stored.coverage_shares_version is None    # still stale, still heals
    finally:
        proj.close()


def test_the_median_depth_heals_off_the_same_read(tmp_path):
    """The third measurement off the same map: the depth at least half the
    picture is at or below, which is what κ-σ's reach is judged on."""
    from seestack.coverage_backfill import backfill_coverage_shares

    fits_path = tmp_path / "out" / "m42.fits"
    cov = np.full((200, 200), 3.0, dtype=np.float32)
    cov[80:120, 80:120] = 12.0            # a small four-way overlap corner
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), is_mosaic=True))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        backfill_coverage_shares(proj, row)
        assert row.coverage_median_depth == pytest.approx(3.0)
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).coverage_median_depth == pytest.approx(3.0)
    finally:
        proj.close()


def test_an_empty_map_leaves_the_empty_share_null_too(tmp_path):
    """"Nothing covered" is not "100% black": a canvas with no picture on it
    must leave both columns NULL, so every note stays silent."""
    from seestack.coverage_backfill import backfill_coverage_shares

    fits_path = tmp_path / "out" / "m42.fits"
    _write_map(fits_path.with_name("m42_framecov.fits"),
               np.zeros((50, 50), dtype=np.float32))

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        backfill_coverage_shares(proj, row)
        assert row.uncovered_frac is None
        assert row.coverage_thin_frac is None
    finally:
        proj.close()


def test_a_read_only_database_still_answers_the_empty_share(tmp_path, monkeypatch):
    """Same care point as the thin share: it writes from a read path, so a DB it
    can't write costs the panel its advice — never an error at the user."""
    import sqlite3

    from seestack.coverage_backfill import backfill_coverage_shares

    fits_path = tmp_path / "out" / "m42.fits"
    cov = np.full((100, 100), 6.0, dtype=np.float32)
    cov[:40] = 0.0
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)

        def _refuse(*_a, **_k):
            raise sqlite3.OperationalError("attempt to write a readonly database")

        monkeypatch.setattr(Project, "set_stack_uncovered_frac", _refuse)
        backfill_coverage_shares(proj, row)
        assert row.uncovered_frac == pytest.approx(0.4)
        monkeypatch.undo()
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).uncovered_frac is None
    finally:
        proj.close()


def test_a_read_only_database_still_answers_the_question(tmp_path, monkeypatch):
    """Care point 4: it writes to the project DB from a read path, so a DB it
    can't write must cost the panel its advice — not raise at the user."""
    import sqlite3

    fits_path = tmp_path / "out" / "m42.fits"
    cov = _ragged_border_coverage()
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)

        def _refuse(*_a, **_k):
            raise sqlite3.OperationalError("attempt to write a readonly database")

        monkeypatch.setattr(Project, "set_stack_coverage_thin_frac", _refuse)
        share = backfill_coverage_thin_frac(proj, row)
        # The note is still made — it just isn't remembered.
        assert share == pytest.approx(coverage_thin_fraction(cov))
        assert row.coverage_thin_frac == pytest.approx(share)
        monkeypatch.undo()
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).coverage_thin_frac is None
    finally:
        proj.close()


def test_the_healed_number_is_the_one_the_stacker_would_have_stamped(tmp_path):
    """Pinned by construction rather than by a literal: whatever the measure
    does, the healed row and a fresh stack of the same coverage must agree, so
    an old run and a re-stacked one can never give different advice."""
    rng = np.random.default_rng(7)
    cov = np.round(rng.uniform(0.0, 20.0, size=(120, 90))).astype(np.float32)
    fits_path = tmp_path / "out" / "m42.fits"
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_thin_frac(proj, row) == pytest.approx(
            coverage_thin_fraction(cov))
    finally:
        proj.close()
