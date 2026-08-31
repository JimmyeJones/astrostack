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


def _lopsided_coverage() -> np.ndarray:
    """Two thirds of the canvas got one frame, the last third twelve — the
    ragged shape the note exists to catch (`coverage_thin_fraction` reads ⅔)."""
    cov = np.ones((300, 300), dtype=np.float32)
    cov[:, 200:] = 12.0
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
    cov = _lopsided_coverage()
    _write_map(fits_path.with_name("m42_framecov.fits"), cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert row.coverage_thin_frac is None  # what the owner's library looks like

        share = backfill_coverage_thin_frac(proj, row)
        assert share == pytest.approx(coverage_thin_fraction(cov))
        assert share == pytest.approx(2 / 3, abs=0.01)
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
    frames = _lopsided_coverage()
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
    cov = _lopsided_coverage()
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


def test_a_run_that_already_has_a_share_is_left_exactly_alone(tmp_path):
    """The common case — every run stacked since v0.320.2 — must cost nothing:
    no map read, no write, and certainly no re-measurement."""
    fits_path = tmp_path / "out" / "m42.fits"
    # A map that would measure ⅔ if it were ever read.
    _write_map(fits_path.with_name("m42_framecov.fits"), _lopsided_coverage())

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), coverage_thin_frac=0.004))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_thin_frac(proj, row) == pytest.approx(0.004)
        assert row.coverage_thin_frac == pytest.approx(0.004)
    finally:
        proj.close()


def test_a_read_only_database_still_answers_the_question(tmp_path, monkeypatch):
    """Care point 4: it writes to the project DB from a read path, so a DB it
    can't write must cost the panel its advice — not raise at the user."""
    import sqlite3

    fits_path = tmp_path / "out" / "m42.fits"
    cov = _lopsided_coverage()
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
