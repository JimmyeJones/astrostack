"""``auto_reject`` must size its method from the samples that land on a *pixel*.

Every threshold in the auto outlier-rejection picker is a statement about how
many samples overlap at one pixel: κ-σ cannot pull a lone trail out of statistics
that still include it until about :func:`kappa_min_frames` samples, and the
order-statistic min/max drop needs three to spare two. On a single field those
samples are the whole stack, so the frame count is the right proxy — but a mosaic
panel is a different patch of sky, and a pixel only ever sees its own panel's
subs. A 2×2 mosaic three subs deep therefore presented ``n = 12`` to a test whose
real answer is 3, dispatched κ-σ, and clipped **nothing**.

Audit finding A6. The engine-level fix is :func:`auto_reject_depth`; these tests
pin both the rule and the picture it produces.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.stack.stacker import (
    AUTO_REJECT_PANEL_MIN_FRAMES,
    MIN_MAX_MIN_FRAMES,
    StackOptions,
    _resolve_auto_reject,
    auto_reject_depth,
    combine_method,
    kappa_min_frames,
    rejection_reach,
    run_stack,
)
from tests.synth import make_synth_wcs_text, write_seestar_fits

# Panel step, in degrees. Well beyond ``PANEL_LINK_DIST_DEG`` (0.25), so the
# panels cluster apart while a dither would not.
_STEP_DEG = 0.5
_BASE = (83.6, -5.4)
_PIXSCALE = 5.0
_W, _H = 480, 320


def _panels(n_side: int) -> list[tuple[float, float]]:
    return [(_BASE[0] + i * _STEP_DEG, _BASE[1] + j * _STEP_DEG)
            for j in range(n_side) for i in range(n_side)]


# --- the rule ---------------------------------------------------------------

def test_a_single_field_has_no_panel_depth_so_nothing_changes():
    """The whole no-regression guarantee in one line: a target that doesn't split
    into panels returns ``None``, which every caller reads as "use the frame
    count", i.e. exactly the behaviour every single-field stack has always had."""
    radecs = [(_BASE[0] + 0.01 * i, _BASE[1]) for i in range(20)]  # a dither
    assert auto_reject_depth(radecs) is None


def test_an_unsolved_target_has_no_panel_depth():
    assert auto_reject_depth([(None, None)] * 12) is None


def test_a_mosaic_reports_its_thinnest_substantial_panel():
    """Four panels: 3, 3, 20 and 20 subs. The depth is the *thinnest* — that is
    the panel whose trails would otherwise survive, and the method is one global
    choice for the whole canvas."""
    radecs: list[tuple[float | None, float | None]] = []
    for (ra, dec), count in zip(_panels(2), (3, 3, 20, 20), strict=True):
        radecs += [(ra, dec)] * count
    assert auto_reject_depth(radecs) == 3


def test_a_panel_too_thin_to_be_helped_does_not_drag_the_depth_down():
    """A stray mis-solved sub sitting on its own must not pose as a one-frame
    panel and demote a deep mosaic: below ``AUTO_REJECT_PANEL_MIN_FRAMES`` neither
    method could act on it anyway, so it cannot change the answer."""
    assert AUTO_REJECT_PANEL_MIN_FRAMES == MIN_MAX_MIN_FRAMES
    radecs: list[tuple[float | None, float | None]] = []
    for ra, dec in _panels(2):
        radecs += [(ra, dec)] * 40
    radecs.append((_BASE[0] + 4.0, _BASE[1] + 4.0))   # one stray pointing
    assert auto_reject_depth(radecs) == 40


def test_the_picker_reads_the_depth_not_the_frame_count():
    """The defect itself, at the unit that decides it. Twelve frames clears the
    κ=3 threshold of 11, so the old call dispatched κ-σ; three samples per pixel
    does not, so the fixed call picks the order-statistic drop that works there."""
    opts = StackOptions(auto_reject=True)
    assert kappa_min_frames(3.0) == 11

    blind = _resolve_auto_reject(opts, 12)                  # the old, frame-count call
    assert blind.sigma_clip is True and blind.min_max_reject is False
    assert combine_method(blind, 12) == "sigma-clip"

    seeing = _resolve_auto_reject(opts, 12, depth=3)        # the same stack, per-pixel
    assert seeing.sigma_clip is False and seeing.min_max_reject is True
    assert combine_method(seeing, 12) == "min-max-reject"

    # A mosaic deep enough for κ-σ per panel keeps κ-σ, so the change only ever
    # fires where the pass really was blind.
    deep = _resolve_auto_reject(opts, 400, depth=100)
    assert deep.sigma_clip is True and deep.min_max_reject is False

    # And a run that never opted in is untouched whatever the depth.
    manual = StackOptions(auto_reject=False, sigma_clip=True)
    assert _resolve_auto_reject(manual, 12, depth=3) is manual


def test_the_pre_run_warning_answers_for_the_pixels_not_the_target():
    """``rejection_reach`` feeds the Stack form's "can this remove a satellite
    trail?" line. On a mosaic it has to answer per-pixel too, or the form
    reassures a user about a stack that will clip nothing."""
    manual = StackOptions()  # the plain sigma_clip default, no auto-reject
    # 12 frames reads as protected until you ask about one panel of three.
    assert rejection_reach(manual, 12).reaches is True
    shallow = rejection_reach(manual, 12, depth=3)
    assert shallow.method == "sigma-clip"
    assert shallow.reaches is False
    assert shallow.lone_outlier_min_frames == kappa_min_frames(3.0)
    # With auto-reject on, the same mosaic resolves to a method that *does* reach.
    auto = rejection_reach(StackOptions(auto_reject=True), 12, depth=3)
    assert auto.method == "min-max-reject"
    assert auto.reaches is True
    # No depth supplied → byte-for-byte the old answer.
    assert rejection_reach(manual, 12).reaches is rejection_reach(
        manual, 12, depth=None).reaches


def test_the_depth_survives_dithering_and_stays_cheap_at_the_owners_scale():
    """A real mosaic is thousands of *dithered* subs, and this runs inside
    ``estimate_stack`` — which the Stack form calls on every option change.

    Clustering the raw pointings is O(n²) in pure Python: 2.4 s on the owner's
    largest target. Clustering the *distinct* pointings instead collapses that to
    the panel count, and the dither must not defeat the snap that makes it work.
    """
    import time

    rng = np.random.default_rng(5)
    radecs: list[tuple[float | None, float | None]] = []
    for i in range(3):
        for j in range(3):
            count = 3 if (i, j) == (0, 0) else 600   # one thin panel, eight deep
            for _ in range(count):
                radecs.append((
                    _BASE[0] + i * _STEP_DEG + float(rng.uniform(-0.03, 0.03)),
                    _BASE[1] + j * _STEP_DEG + float(rng.uniform(-0.03, 0.03)),
                ))
    assert len(radecs) > 4000

    started = time.perf_counter()
    depth = auto_reject_depth(radecs)
    elapsed = time.perf_counter() - started

    assert depth == 3          # the dither stayed inside its panel, the snap held
    # Generous by ~100x against the measured 0.004 s, so it pins the collapse from
    # quadratic-in-subs without being a timing flake.
    assert elapsed < 0.5, elapsed


# --- the picture ------------------------------------------------------------

def _build(tmp_path, panels, subs_per_panel: int, streak_at: int) -> Project:
    proj = Project.create(tmp_path / "p", name="a6")
    raws = tmp_path / "raws"
    raws.mkdir()
    k = 0
    for ra, dec in panels:
        for _ in range(subs_per_panel):
            path = write_seestar_fits(
                raws / f"f{k}.fit", add_wcs=True, seed=7, noise_seed=300 + k,
                n_stars=10, streak=(k == streak_at),
                ra_center_deg=ra, dec_center_deg=dec, pixscale_arcsec=_PIXSCALE)
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=_W, height_px=_H, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    ra_center_deg=ra, dec_center_deg=dec, pixscale_arcsec=_PIXSCALE),
                ra_center_deg=ra, dec_center_deg=dec))
            k += 1
    return proj


def _stack(proj, **overrides):
    from astropy.io import fits

    opts = dict(background_flatten=False, suppress_hot_pixels=False,
                max_workers=2, output_name="out", mosaic_canvas="union")
    opts.update(overrides)
    result = run_stack(proj, StackOptions(**opts))
    with fits.open(result.fits_path) as hdul:
        return np.asarray(hdul[0].data, np.float32), dict(hdul[0].header)


def test_a_shallow_mosaics_satellite_trail_is_actually_removed(tmp_path):
    """End-to-end, through the public ``run_stack``: a 2×2 mosaic three subs deep
    with one streaked sub.

    Measured against an otherwise identical streak-free stack — the honest
    residual, since the stars are in both. Before the fix ``auto_reject``
    dispatched κ-σ, recorded ``REJFRAC 0.0`` (it rejected *nothing*) and left the
    trail at **1,030 ADU**; after it, the same stack picks the order-statistic
    drop and leaves **19**.
    """
    panels = _panels(2)
    dirty_proj = _build(tmp_path / "dirty", panels, 3, streak_at=0)
    try:
        dirty, header = _stack(dirty_proj, auto_reject=True)
    finally:
        dirty_proj.close()
    clean_proj = _build(tmp_path / "clean", panels, 3, streak_at=-1)
    try:
        clean, _ = _stack(clean_proj, auto_reject=True)
    finally:
        clean_proj.close()

    # The method the run actually took, from its own provenance card.
    assert header["REJMODE"] == "min-max-reject"
    assert float(header["REJFRAC"]) > 0.0      # ...and it really dropped samples

    residual = dirty[1] - clean[1]
    finite = residual[np.isfinite(residual)]
    assert finite.size > 0
    # Fails before at ~1,030; passes after at ~19. The threshold sits an order of
    # magnitude below the broken value and comfortably above the fixed one.
    assert float(np.percentile(finite, 99.9)) < 100.0


def test_a_single_field_stack_of_the_same_depth_is_unchanged(tmp_path):
    """The no-regression half, end-to-end: twelve subs of *one* field still take
    κ-σ, because there every one of those twelve lands on the same pixel."""
    proj = _build(tmp_path / "single", [_BASE], 12, streak_at=0)
    try:
        _img, header = _stack(proj, auto_reject=True)
    finally:
        proj.close()
    assert header["REJMODE"] == "sigma-clip"
