"""Healing an older mosaic run's panel-flatness number from what it wrote.

``stack_runs.seam_residual`` arrived with schema 15, so every mosaic the owner
stacked before that reads NULL — and NULL is "no verdict" everywhere it is read
(the "How's my stack?" seam notes, the History chip, the Gallery card). Unlike
the capture dates, this one is recoverable: it is a measurement over the master
and the coverage map the run already wrote, both of which are still on disk.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.bg.coverage_leveling import level_by_coverage, measure_seam_residual
from seestack.coverage_backfill import (
    _SEAM_MAX_STEP,
    _seam_read_step,
    backfill_seam_residual,
)
from seestack.io.project import Project, StackRunRow
from seestack.stackhealth import seam_verdict


def _run(**kw) -> StackRunRow:
    base = dict(
        id=None, timestamp_utc="2026-09-01T00:00:00+00:00", output_basename="m31",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=40,
        canvas_h=600, canvas_w=800, coverage_min=1, coverage_max=4,
        options_json="{}", is_mosaic=True, seam_residual=None,
    )
    base.update(kw)
    return StackRunRow(**base)


def _panel_scene(offsets=(0.0, 15.0, 30.0, 45.0), noise=2.0, neb_amp=60.0,
                 stars=300, h=600, w=800, seed=3):
    """The same 4-panel canvas ``measure_seam_residual``'s own thresholds were
    set on (``tests/test_coverage_leveling.py``): rising per-panel sky offsets, a
    nebula across the middle panels, stars everywhere."""
    rng = np.random.default_rng(seed)
    cov = np.zeros((h, w), dtype=np.int32)
    for i, cols in enumerate(np.array_split(np.arange(w), 4)):
        cov[:, cols] = i + 1
    rgb = rng.normal(0.0, noise, size=(h, w, 3)).astype(np.float32)
    for lvl, off in zip((1, 2, 3, 4), offsets, strict=True):
        m = cov == lvl
        for c in range(3):
            rgb[..., c][m] += off
    yy, xx = np.mgrid[0:h, 0:w]
    neb = neb_amp * np.exp(-(((yy - h / 2) / 120.0) ** 2
                             + ((xx - w / 2) / 200.0) ** 2))
    for c, k in enumerate((1.0, 0.7, 0.5)):
        rgb[..., c] += (neb * k).astype(np.float32)
    for _ in range(stars):
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(6, w - 6))
        rgb[y - 2:y + 3, x - 2:x + 3, :] += float(rng.uniform(200, 4000))
    return rgb, cov


def _write_outputs(fits_path: Path, rgb: np.ndarray, cov: np.ndarray,
                   *, frame_cov: bool = True) -> None:
    """The master and the coverage siblings a mosaic run leaves on disk: the
    master as the ``(C, H, W)`` cube ``write_stack_outputs`` writes."""
    from astropy.io import fits

    fits_path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(
        data=np.transpose(np.asarray(rgb, dtype=np.float32), (2, 0, 1))
    ).writeto(fits_path, overwrite=True)
    fits.PrimaryHDU(data=np.asarray(cov, dtype=np.float32)).writeto(
        fits_path.with_name(f"{fits_path.stem}_coverage.fits"), overwrite=True)
    if frame_cov:
        fits.PrimaryHDU(data=np.asarray(cov, dtype=np.float32)).writeto(
            fits_path.with_name(f"{fits_path.stem}_framecov.fits"),
            overwrite=True)


def _project_with_run(tmp_path: Path, run: StackRunRow) -> tuple[Project, int]:
    proj = Project.create(tmp_path / "t", name="T")
    return proj, proj.add_stack_run(run)


def _seamed_scene(bump: float):
    """A correctly-leveled canvas with one coverage level left stranded — the
    realistic shape of the failure the measurement exists for."""
    rgb, cov = _panel_scene()
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    out[cov == 3] += bump
    return out, cov


# --- the heal itself --------------------------------------------------------


def test_an_old_mosaic_gets_its_panel_verdict_back_from_disk(tmp_path):
    """A NULL row plus the master and coverage map beside it answers the
    question the run never got to record."""
    rgb, cov = _seamed_scene(6.0)          # 3x the scene's own 2 ADU grain
    fits_path = tmp_path / "out" / "m31.fits"
    _write_outputs(fits_path, rgb, cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert row.seam_residual is None    # what the owner's library looks like

        ratio = backfill_seam_residual(proj, row)
        assert ratio is not None
        assert seam_verdict(ratio) == "check"
        # The caller's copy grades like a freshly-stacked run…
        assert row.seam_residual == pytest.approx(ratio)
        # …and so does every later read, without touching the master again.
        again = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert again.seam_residual == pytest.approx(ratio)
    finally:
        proj.close()


def test_a_mosaic_whose_panels_matched_gets_the_compliment_too(tmp_path):
    """The heal restores both halves of the verdict, not only the warning."""
    rgb, cov = _panel_scene()
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    fits_path = tmp_path / "out" / "flat.fits"
    _write_outputs(fits_path, out, cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        ratio = backfill_seam_residual(proj, row)
        assert ratio is not None
        assert seam_verdict(ratio) == "flat"
    finally:
        proj.close()


@pytest.mark.parametrize("bump,expected", [(6.0, "check"), (0.0, "flat")])
def test_the_healed_number_is_the_one_the_stacker_would_have_stamped(
        tmp_path, bump, expected):
    """Pinned against the full-resolution measurement ``run_stack`` makes in
    memory, not against a literal: an old run and a re-stacked one must never
    give different advice about the same picture."""
    rgb, cov = _seamed_scene(bump)
    fits_path = tmp_path / "out" / "m31.fits"
    _write_outputs(fits_path, rgb, cov)

    in_memory = measure_seam_residual(rgb, cov, frame_coverage=cov)
    assert in_memory is not None

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        healed = backfill_seam_residual(proj, row)
    finally:
        proj.close()
    assert healed is not None
    assert healed == pytest.approx(in_memory.ratio, rel=0.035)
    assert seam_verdict(healed) == seam_verdict(in_memory.ratio) == expected


def test_a_bigger_canvas_is_read_strided_and_still_agrees(tmp_path):
    """The read is capped in size, so a canvas past the cap is decimated by
    striding — which samples the same pixels rather than averaging them, so the
    step and the grain the ratio divides keep their scale. Pinned against the
    full-resolution answer for the same picture."""
    rgb, cov = _panel_scene(h=1800, w=2400, stars=900)
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    out[cov == 3] += 3.0
    fits_path = tmp_path / "out" / "big.fits"
    _write_outputs(fits_path, out, cov)

    in_memory = measure_seam_residual(out, cov, frame_coverage=cov)
    assert in_memory is not None
    assert _seam_read_step(1800, 2400) > 1, "the point of the case"

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), canvas_h=1800, canvas_w=2400))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        healed = backfill_seam_residual(proj, row)
    finally:
        proj.close()
    assert healed is not None
    assert healed == pytest.approx(in_memory.ratio, rel=0.035)
    assert seam_verdict(healed) == seam_verdict(in_memory.ratio)


def test_the_weighted_map_alone_is_enough(tmp_path):
    """Runs old enough to predate the frame-count sibling still wrote the
    weighted one — which is what ``run_stack`` passes as the levels anyway."""
    rgb, cov = _seamed_scene(6.0)
    fits_path = tmp_path / "out" / "m31.fits"
    _write_outputs(fits_path, rgb, cov, frame_cov=False)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert seam_verdict(backfill_seam_residual(proj, row)) == "check"
    finally:
        proj.close()


# --- when it must stay silent ------------------------------------------------


def test_a_single_field_run_is_free_and_says_nothing(tmp_path, monkeypatch):
    """A run the stacker recorded as a single field has one coverage level and
    no join to compare. It must decline *before* opening anything: this runs on
    the ordinary Target page, for every non-mosaic stack the owner has."""
    rgb, cov = _seamed_scene(6.0)
    fits_path = tmp_path / "out" / "single.fits"
    _write_outputs(fits_path, rgb, cov)

    import seestack.coverage_backfill as cb

    def _never(*_a, **_k):  # pragma: no cover - the assertion is that it isn't
        raise AssertionError("a single-field run must not read the master")

    monkeypatch.setattr(cb, "_load_strided_rgb", _never)
    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), is_mosaic=False))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_seam_residual(proj, row) is None
        assert row.seam_residual is None
    finally:
        proj.close()


def test_a_run_too_old_to_know_whether_it_was_a_mosaic_stays_quiet(tmp_path):
    """``is_mosaic`` arrived with schema 8 and reads NULL below it. Guessing
    "mosaic" from the coverage map would be inventing the very fact that decides
    whether the app is entitled to speak — so an unclassified run keeps its
    NULL, exactly as it does today."""
    rgb, cov = _seamed_scene(6.0)
    fits_path = tmp_path / "out" / "unknown.fits"
    _write_outputs(fits_path, rgb, cov)

    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(fits_path), is_mosaic=None))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_seam_residual(proj, row) is None
    finally:
        proj.close()


def test_a_missing_master_is_not_an_error(tmp_path):
    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(tmp_path / "out" / "gone.fits")))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_seam_residual(proj, row) is None
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).seam_residual is None
    finally:
        proj.close()


def test_a_master_with_no_coverage_sibling_left_stays_null(tmp_path):
    """Which levels the picture has is not knowable from the picture, so a
    tidied-away coverage map means no verdict — never one measured some other
    way."""
    from astropy.io import fits

    rgb, cov = _seamed_scene(6.0)
    fits_path = tmp_path / "out" / "lonely.fits"
    fits_path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=np.transpose(rgb, (2, 0, 1))).writeto(fits_path)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_seam_residual(proj, row) is None
    finally:
        proj.close()


def test_a_coverage_map_from_another_canvas_is_refused(tmp_path):
    """A restored backup or a hand-tidied output dir can leave a sibling that
    doesn't belong to this picture. Measuring one image against another's map
    would produce a confident, wrong verdict."""
    from astropy.io import fits

    rgb, cov = _seamed_scene(6.0)
    fits_path = tmp_path / "out" / "mismatched.fits"
    fits_path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=np.transpose(rgb, (2, 0, 1))).writeto(fits_path)
    fits.PrimaryHDU(data=cov[:100, :100].astype(np.float32)).writeto(
        fits_path.with_name("mismatched_coverage.fits"))

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_seam_residual(proj, row) is None
    finally:
        proj.close()


def test_a_run_that_already_has_a_verdict_is_left_exactly_alone(tmp_path,
                                                               monkeypatch):
    """The common case — every mosaic stacked since v0.233.0 — must cost
    nothing: no read, no write, and certainly no re-measurement."""
    import seestack.coverage_backfill as cb

    def _never(*_a, **_k):  # pragma: no cover - the assertion is that it isn't
        raise AssertionError("a run with a verdict must not be re-measured")

    monkeypatch.setattr(cb, "_load_strided_rgb", _never)
    proj, run_id = _project_with_run(
        tmp_path, _run(fits_path=str(tmp_path / "whatever.fits"),
                       seam_residual=0.42))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_seam_residual(proj, row) == pytest.approx(0.42)
    finally:
        proj.close()


def test_a_read_only_database_still_answers_the_question(tmp_path, monkeypatch):
    """It writes to the project DB from a read path, so a DB it can't write must
    cost the panel its memory of the answer — not raise at the user."""
    import sqlite3

    rgb, cov = _seamed_scene(6.0)
    fits_path = tmp_path / "out" / "m31.fits"
    _write_outputs(fits_path, rgb, cov)

    proj, run_id = _project_with_run(tmp_path, _run(fits_path=str(fits_path)))
    try:
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)

        def _refuse(*_a, **_k):
            raise sqlite3.OperationalError("attempt to write a readonly database")

        monkeypatch.setattr(Project, "set_stack_seam_residual", _refuse)
        ratio = backfill_seam_residual(proj, row)
        assert ratio is not None and row.seam_residual == pytest.approx(ratio)
        monkeypatch.undo()
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).seam_residual is None
    finally:
        proj.close()


# --- how big a master it will read -------------------------------------------


def test_a_small_canvas_is_read_whole():
    """Nothing is decimated until it has to be, so a canvas already inside the
    working size gets the identical full-resolution measurement."""
    assert _seam_read_step(600, 800) == 1
    assert _seam_read_step(1080, 1500) == 1


def test_the_stride_is_capped_where_the_answer_starts_to_drift():
    """Past stride 4 the standard-error deduction begins to eat real seam, so
    the stride stops growing (see the measured table on the constants) even
    though the canvas would call for more."""
    assert _seam_read_step(4500, 6000) == _SEAM_MAX_STEP     # asks for 4
    assert _seam_read_step(9000, 12000) == _SEAM_MAX_STEP    # asks for 8


def test_a_canvas_too_big_to_hold_keeps_its_null():
    """With the stride capped, a big enough master would cost more memory than
    a read-path heal may spend — so it waits for its next stack instead."""
    assert _seam_read_step(40_000, 60_000) is None
    assert _seam_read_step(0, 100) is None
