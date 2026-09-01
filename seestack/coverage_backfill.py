"""Fill in an older stack run's coverage-derived measurements from what it wrote.

``stack_runs`` has grown a series of measured columns, and each one arrived with a
schema bump that leaves every *existing* run NULL. The code is consistent and
correct about what NULL means — "unknown, so say nothing" — so each addition
silently makes the owner's whole existing library mute on that subject until
every target happens to be stacked again.

It does not have to wait, for the columns whose input is *still on disk beside
the master*. Both numbers healed here are pure functions of the per-pixel
coverage map (and, for the seam, the master) that the run already wrote, so each
can be computed once, from disk, and written back to the row — after which the
run answers like any freshly-stacked one:

``coverage_thin_frac`` (schema 20)
    The number "How's my stack?" judges a ragged border on — the share of the
    picture covered by far fewer frames than the best-covered part. The panel
    reads NULL as "say nothing" deliberately: the test it replaced fired on every
    stack the app had ever made, so re-using it on old runs would mean knowingly
    repeating a false alarm.

``seam_residual`` (schema 15)
    How flat a **mosaic's** panel joins came out, in units of the picture's own
    grain — the one mosaic failure mode a beginner can see but not diagnose. NULL
    reads as "no verdict" on the health panel, the History chip and the Gallery
    card alike, so a mosaic stacked before the upgrade simply never says whether
    its panels matched.

Both heals are deliberately **lazy**: one read for one run, on the request that
is already grading it. A sweep over the library at startup would turn the first
"How's my stack?" on a big library into a stall, for advice about runs nobody is
looking at. And neither ever *substitutes* a different measurement — when the
input is gone the row stays NULL and the app stays silent.

**Audited, 2026-09-01 — the other later-added columns and why they are not here.**
``stack_fwhm_px`` (14) needs a star fit over the master: real work, and it
belongs behind an explicit action rather than a lazy read. ``capture_start_utc``
/ ``capture_end_utc`` (18) and ``capture_hours_json`` (19) are functions of
*which frames that run used*, which nothing on disk records — recovering them
from today's accepted frames would be a guess wearing a fact's clothes.
``noise_sigma`` (6) is recomputable from the master but is measured from
adjacent-pixel differences, so it cannot be taken off a decimated read, and the
runs affected predate every column below it. And the tempting shortcut —
reading the number off the master's own FITS header — does **not** work: the
``BKGSIGMA``/``STKFWHM``/``SEAMRES``/``CALSTAT`` cards were each added in the
same change as their column (``NROUGHAL`` leads its column by one patch release,
``CALSTAT`` by 50 minutes), so a run old enough to have a NULL has no card
either.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

    from seestack.io.project import Project, StackRunRow

log = logging.getLogger(__name__)


def backfill_coverage_thin_frac(project: Project,
                                run: StackRunRow) -> float | None:
    """Compute ``run``'s thin-coverage share from its coverage sibling, record it
    on the row, and return it — or ``None`` when it can't be known.

    A no-op (returns the stored value) for a run that already has one, so callers
    can call it unconditionally. ``run`` is updated in place on success, so the
    caller's copy grades exactly like a freshly-stacked run.

    Which map: the honest per-pixel **frame count** (``{stem}_framecov.fits``)
    when the run wrote one, else the weighted coverage map — the same preference,
    in the same order, that :func:`seestack.stack.stacker.run_stack` itself makes
    when it stamps the column on a new run.

    ``None`` — no master path, no sibling on disk, an unreadable one, or a map
    with nothing covered — leaves the row NULL and the panel silent. It never
    falls back to the ``coverage_min`` test that column replaced.
    """
    if run.coverage_thin_frac is not None:
        return float(run.coverage_thin_frac)
    if not run.fits_path:
        return None

    from seestack.edit.proxy import load_coverage, load_frame_coverage
    from seestack.stack.stacker import coverage_thin_fraction

    cov = load_frame_coverage(run.fits_path)
    if cov is None:
        cov = load_coverage(run.fits_path)
    if cov is None:
        return None
    share = coverage_thin_fraction(cov)
    if share is None:
        return None

    if run.id is not None:
        try:
            project.set_stack_coverage_thin_frac(run.id, share)
        except sqlite3.Error:
            # A read-only DB (or one another process has locked) just means this
            # run pays the map read again next time — never an error to the user,
            # who only asked how their stack looks.
            log.debug("could not record coverage_thin_frac for run %s", run.id,
                      exc_info=True)
    run.coverage_thin_frac = share
    return share


# How far the seam heal may decimate the master before it reads it. The measure
# is a *ratio* of a between-level sky step to the grain inside a level, and
# striding changes neither: it samples the same pixels, unlike an area average,
# which would shrink the grain and inflate the ratio. What it does change is how
# many sky pixels each level's estimate rests on, and the measure deducts that
# standard error from the step it reports — so the answer creeps low as the
# stride grows. Measured on the 4-panel scene the thresholds themselves were set
# on (`tests/test_coverage_leveling.py::_panel_scene`, 900x1200), against the
# full-resolution answer:
#
#     stride       1       2       3       4       6       8
#     seam ~1.0    0.997   0.987   0.961   0.966   0.942   0.879
#     seam ~1.5    1.498   1.487   1.464   1.464   1.443   1.376
#     seam ~23     23.60   23.57   23.55   —       —       23.54
#
# Through stride 4 the drift is under 3.5 %, an order below the gap between the
# "flat" (< 1.0) and "visible" (>= 1.5) bars, so a healed run and a re-stacked
# one give the same verdict. Past it the drift starts to matter, so the stride is
# capped rather than the canvas: a master too big to read within the cap keeps
# its NULL.
_SEAM_TARGET_PX = 1500        # the editor proxy's own cap (seestack.edit.proxy)
_SEAM_MAX_STEP = 4            # measured above; do not raise without re-measuring
_SEAM_MAX_WORK_PX = 12_000_000  # ~140 MB of float32 RGB, the read's own ceiling


def _seam_read_step(height: int, width: int) -> int | None:
    """The stride to read a ``height x width`` master at, or ``None`` when even
    the largest permitted one leaves more pixels than this heal will hold."""
    if height <= 0 or width <= 0:
        return None
    step = max(1, math.ceil(max(height, width) / _SEAM_TARGET_PX))
    if step > _SEAM_MAX_STEP:
        step = _SEAM_MAX_STEP
    if (height // step) * (width // step) > _SEAM_MAX_WORK_PX:
        return None
    return step


def _load_strided_rgb(fits_path: str | Path, step: int) -> np.ndarray | None:
    """Read a master FITS as ``(H, W, 3)`` float32, taking every ``step``-th
    pixel, or ``None`` when it carries no usable image.

    Strided off the memory map one channel at a time — the shape
    :func:`seestack.render.thumbnail.load_stack_rgb` settled on — so the only
    full-canvas allocation this heal makes is the small strided output, not the
    big-endian cube it came from. Striding, not averaging: see the constants
    above.
    """
    from astropy.io import fits as _fits

    try:
        with _fits.open(fits_path, memmap=True) as hdul:
            data = next((h.data for h in hdul if h.data is not None), None)
            if data is None:
                return None
            if data.ndim == 3 and data.shape[0] > 1:      # (channels, H, W)
                planes = [data[c] for c in range(min(data.shape[0], 3))]
            elif data.ndim == 3:
                planes = [data[0]]
            elif data.ndim == 2:
                planes = [data]
            else:
                return None
            out = [np.asarray(p[::step, ::step], dtype=np.float32)
                   for p in planes]
    except (OSError, ValueError, IndexError):
        return None
    if len(out) == 1:
        out = [out[0], out[0], out[0]]
    return np.stack(out, axis=-1)


def backfill_seam_residual(project: Project,
                           run: StackRunRow) -> float | None:
    """Measure how flat an older **mosaic** run's panel joins came out, from the
    master and coverage map it already wrote; record it and return it — or
    ``None`` when it can't be known.

    A no-op (returns the stored value) for a run that already has one, and free —
    no disk touched at all — for a run the stacker recorded as a single field,
    which has no joins to compare and never had a seam residual to lose.

    ``None`` — a single-field or unclassified run, no master path, a missing or
    unreadable master or coverage sibling, a canvas too big to read within the
    stride cap, or a canvas whose levels can't be measured — leaves the row NULL
    and every seam surface silent, which is exactly what they do today.
    """
    if run.seam_residual is not None:
        return float(run.seam_residual)
    # A run the stacker did not record as a mosaic has one coverage level and no
    # join to compare: the measurement would decline anyway, so decline first and
    # never open a file for it. A run too old to carry the flag (schema < 8) is
    # unclassified, not single-field — but guessing "mosaic" from the coverage
    # map would be inventing the very fact that decides whether to speak.
    if not run.is_mosaic or not run.fits_path:
        return None

    from pathlib import Path as _Path

    from seestack.bg.coverage_leveling import measure_seam_residual
    from seestack.edit.proxy import load_coverage, load_frame_coverage

    master = _Path(run.fits_path)
    if not master.exists():
        return None
    try:
        h, w = int(run.canvas_h), int(run.canvas_w)
    except (TypeError, ValueError):
        return None
    step = _seam_read_step(h, w)
    if step is None:
        return None

    rgb = _load_strided_rgb(master, step)
    if rgb is None:
        return None
    # The same two maps, in the same order of preference, that ``run_stack``
    # hands the measurement: the weighted coverage decides the levels, the honest
    # frame count refines them when the run wrote one.
    cov = load_coverage(master, step=step)
    if cov is None:
        return None
    frame_cov = load_frame_coverage(master, step=step)
    if cov.shape != rgb.shape[:2] or (
            frame_cov is not None and frame_cov.shape != rgb.shape[:2]):
        # A sibling from a different canvas (a hand-tidied output dir, a restored
        # backup) is not this picture's coverage — say nothing rather than
        # measure one image against another's map.
        return None
    try:
        result = measure_seam_residual(
            rgb, cov, frame_coverage=frame_cov, proxy_scale=float(step))
    except Exception:  # noqa: BLE001 — a diagnostic must never reach the user
        log.debug("could not measure seam residual for run %s", run.id,
                  exc_info=True)
        return None
    if result is None or not math.isfinite(float(result.ratio)):
        return None
    # Rounded exactly as ``_compute_seam_residual`` rounds it, so a healed row and
    # a freshly-stacked one are the same kind of number.
    ratio = round(float(result.ratio), 4)

    if run.id is not None:
        try:
            project.set_stack_seam_residual(run.id, ratio)
        except sqlite3.Error:
            # A read-only DB (or one another process has locked) just means this
            # run pays the read again next time — never an error to the user.
            log.debug("could not record seam_residual for run %s", run.id,
                      exc_info=True)
    run.seam_residual = ratio
    return ratio
