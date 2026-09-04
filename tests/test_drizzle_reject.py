"""Two-pass drizzle outlier rejection (``StackOptions.drizzle_reject``).

Single-pass drizzle keeps every contribution, so a satellite/plane trail or
cosmic ray in one sub lands permanently in the drizzled output. The two-pass
mode builds per-output-pixel contribution statistics first (value and value²
drizzled under the same weights), then re-drizzles with contributions outside
``mean ± κ·σ`` zero-weighted. These tests pin down the astro-correctness
properties: trails are rejected, star cores are NOT eaten under dithering,
low-coverage pixels are never clipped, and NaN/coverage semantics hold.
"""

from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("drizzle")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.io.wcs_io import wcs_from_text  # noqa: E402
from seestack.stack.drizzle_path import (  # noqa: E402
    _MIN_REJECT_NEFF,
    _VAR_RESOLUTION_FACTOR,
    DrizzleParams,
    DrizzleStacker,
    _clip_tolerance,
)
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def _plain_wcs(dx=0.0, dy=0.0, width=40, height=30):
    """A bare TAN WCS whose reference pixel is offset by ``(dx, dy)`` px."""
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [83.6, -5.4]
    w.wcs.crpix = [width / 2 + 0.5 + dx, height / 2 + 0.5 + dy]
    w.wcs.cdelt = [-5.0 / 3600.0, 5.0 / 3600.0]
    return w


def _wcs(width=100, height=80):
    return wcs_from_text(make_synth_wcs_text(width=width, height=height))


def _stack_with_clip(frames, wcs, *, kappa=3.0, reject=True):
    """Drizzle ``frames`` (H, W, 3 arrays) with/without two-pass rejection."""
    params = DrizzleParams(scale=1.0, pixfrac=1.0)
    shape = frames[0].shape[:2]
    clip = None
    if reject:
        stats = DrizzleStacker(wcs, shape, params, compute_stats=True)
        for f in frames:
            stats.add_frame(f, wcs)
        clip = stats.clip_reference(kappa)
    final = DrizzleStacker(wcs, shape, params)
    for f in frames:
        final.add_frame(f, wcs, clip=clip)
    return final.result()


def test_reject_clips_outlier_block_exactly():
    """15 flat frames + one with a bright block: the block must come out at
    the clean value (outlier zero-weighted), not the contaminated mean."""
    wcs = _wcs()
    clean = np.full((80, 100, 3), 100.0, dtype=np.float32)
    dirty = clean.copy()
    dirty[30:40, 40:60, :] = 5000.0
    frames = [clean.copy() for _ in range(15)] + [dirty]

    contaminated = _stack_with_clip(frames, wcs, reject=False)
    # Without rejection the block is diluted in: (15·100 + 5000)/16 = 406.25.
    assert contaminated[35, 50, 1] == pytest.approx(406.25, rel=1e-3)

    result = _stack_with_clip(frames, wcs, reject=True)
    # With rejection the outlier is dropped: mean of the 15 clean frames.
    assert result[35, 50, 1] == pytest.approx(100.0, rel=1e-3)
    # Pixels the outlier frame agreed on are kept — still the mean of 16.
    assert result[10, 10, 1] == pytest.approx(100.0, rel=1e-3)


def test_reject_keeps_all_below_min_coverage():
    """With only 2 overlapping frames σ is meaningless — rejection must be
    inert (per-pixel n_eff gate), even for a huge outlier."""
    wcs = _wcs()
    frames = [
        np.full((80, 100, 3), 100.0, dtype=np.float32),
        np.full((80, 100, 3), 5000.0, dtype=np.float32),
    ]
    with_reject = _stack_with_clip(frames, wcs, reject=True)
    without = _stack_with_clip(frames, wcs, reject=False)
    np.testing.assert_allclose(
        with_reject[5:-5, 5:-5], without[5:-5, 5:-5], rtol=1e-5
    )


def test_reject_preserves_single_coverage_and_nan():
    """A strip covered by only one frame must survive rejection untouched, and
    a never-covered region must stay NaN."""
    wcs = _wcs()
    base = np.full((80, 100, 3), 100.0, dtype=np.float32)
    frames = []
    for _ in range(5):
        f = base.copy()
        f[:, 80:] = np.nan  # nobody covers the right strip…
        frames.append(f)
    lone = base.copy()
    lone[:, 80:90] = 300.0  # …except one frame, with a very different value
    lone[:, 90:] = np.nan   # and nobody at all covers the far edge
    frames.append(lone)

    result = _stack_with_clip(frames, wcs, reject=True)
    # Single-coverage strip: kept at the lone frame's value (n_eff < gate).
    assert np.nanmedian(result[10:70, 82:88, :]) == pytest.approx(300.0, rel=1e-3)
    # Fully uncovered region stays NaN.
    assert np.all(np.isnan(result[10:70, 92:98, :]))
    # Well-covered area is the plain mean.
    assert np.nanmedian(result[10:70, 10:70, :]) == pytest.approx(100.0, rel=1e-3)


def test_rejection_counts_tallies_the_clip():
    """The pass-2 drizzler tallies exactly the covered samples it saw and the
    subset its κ-σ clip dropped — a memory-free trust signal for the History
    "rejection clipped ~X%" line, mirroring the κ-σ / min-max accumulators."""
    wcs = _wcs()
    clean = np.full((80, 100, 3), 100.0, dtype=np.float32)
    dirty = clean.copy()
    dirty[30:40, 40:60, :] = 5000.0  # a 10×20×3 = 600-sample outlier block
    frames = [clean.copy() for _ in range(15)] + [dirty]

    params = DrizzleParams(scale=1.0, pixfrac=1.0)
    shape = frames[0].shape[:2]
    stats = DrizzleStacker(wcs, shape, params, compute_stats=True)
    for f in frames:
        stats.add_frame(f, wcs)
    clip = stats.clip_reference(3.0)

    final = DrizzleStacker(wcs, shape, params)
    for f in frames:
        final.add_frame(f, wcs, clip=clip)

    contributed, rejected = final.rejection_counts()
    # Every frame is fully finite and the identity WCS maps every input-pixel
    # centre inside the canvas extent [-0.5, N-0.5] (the tiny float overshoot at
    # the far edge lands well within the outer ½-px band the bounds mask now
    # admits), so the tally is all of 16 × 80×100×3, never more.
    full = 16 * 80 * 100 * 3
    assert 0.999 * full <= contributed <= full
    # Only the dirty frame's outlier block (interior, unaffected by the edge
    # mask) is clipped; the clean frames agree with the mean everywhere (σ=0 →
    # tol=0, exact equality is kept), so exactly 10×20×3 samples are rejected.
    assert rejected == 10 * 20 * 3
    assert rejected / contributed == pytest.approx(600 / contributed)


def test_frame_coverage_counts_a_frame_clipped_in_one_channel_only():
    """Regression: under per-channel κ-σ rejection, ``frame_coverage`` must count
    a frame wherever it contributed to **any** channel — not only channel 0 (red).

    16 clean frames + one whose *red* alone spikes in a block (G/B stay clean).
    Pass 2 zero-weights that frame's red at the block (an outlier) but keeps its
    green/blue. Reading channel-0's weight increase alone (the old behaviour)
    would miss the frame there and report 16 instead of 17 frames/pixel — biasing
    the coverage_min/max "N frames per pixel" diagnostic low and risking a false
    "ragged edges" health note on an otherwise even stack."""
    wcs = _wcs()
    clean = np.full((80, 100, 3), 100.0, dtype=np.float32)
    frames = [clean.copy() for _ in range(16)]
    dirty = clean.copy()
    dirty[30:40, 40:60, 0] = 5000.0  # RED only — an outlier the clip will drop
    frames.append(dirty)

    params = DrizzleParams(scale=1.0, pixfrac=1.0)
    shape = frames[0].shape[:2]
    stats = DrizzleStacker(wcs, shape, params, compute_stats=True)
    for f in frames:
        stats.add_frame(f, wcs)
    clip = stats.clip_reference(3.0)

    final = DrizzleStacker(wcs, shape, params)
    for f in frames:
        final.add_frame(f, wcs, clip=clip)

    fc = final.frame_coverage
    assert fc is not None
    # The dirty frame's red was clipped in the block, but its green/blue landed —
    # so all 17 frames still count there (was 16 when only red was read).
    assert int(fc[32:38, 42:58].min()) == 17
    # And the block matches everywhere else: uniform 17-frame coverage interior.
    assert int(fc[10:70, 10:90].min()) == 17
    # Sanity: the image did drop the red outlier (block red ≈ clean 100, not the
    # contaminated (16·100 + 5000)/17 ≈ 388), while G/B stay clean.
    result = final.result()
    assert result[35, 50, 0] == pytest.approx(100.0, rel=1e-2)
    assert result[35, 50, 1] == pytest.approx(100.0, rel=1e-2)


def test_rejection_counts_zero_without_clip():
    """Single-pass drizzle (no clip) rejects nothing, so the tally stays zero —
    the stacker then stamps no rejection provenance for a plain drizzle."""
    wcs = _wcs()
    frames = [np.full((80, 100, 3), 100.0, dtype=np.float32) for _ in range(5)]
    final = DrizzleStacker(wcs, frames[0].shape[:2], DrizzleParams(scale=1.0, pixfrac=1.0))
    for f in frames:
        final.add_frame(f, wcs)  # clip=None
    assert final.rejection_counts() == (0, 0)


def test_edge_footprint_deposited_within_half_pixel_band():
    """An input pixel whose centre maps into the outer ½-px band [-0.5, 0) still
    lies inside the first output pixel's [-0.5, 0.5] extent, so its drizzle
    footprint must be deposited — the bounds mask keys on the pixel *edges*, not
    the centre indices [0, N-1]. A +0.4-px shift lands input row/column 0 at
    output −0.4; with a tight pixfrac (so neighbours don't bleed across), output
    row/column 0 is covered *only* by that band."""
    out_wcs = _plain_wcs()
    in_wcs = _plain_wcs(dx=0.4, dy=0.4)  # input pixel (0,0) → output (−0.4, −0.4)
    frame = np.full((30, 40, 3), 100.0, dtype=np.float32)
    st = DrizzleStacker(out_wcs, (30, 40), DrizzleParams(scale=1.0, pixfrac=0.1))
    st.add_frame(frame, in_wcs)

    wht = st._drizzlers[0].out_wht
    # The corner and the whole first row/column draw their coverage from the
    # ½-px band; the tighter (index-only) mask dropped them entirely.
    assert wht[0, 0] > 0.0, "corner in the ½-px band must be deposited"
    assert np.all(wht[0, :] > 0.0), "top edge row must be covered"
    assert np.all(wht[:, 0] > 0.0), "left edge column must be covered"


def test_resolution_floor_uses_raw_variance_not_bessel_inflated():
    """The float32 resolution floor (never clip a variance below ULP(m²)) must
    judge the *raw* ``m2 − m²``, independent of the Bessel small-sample
    correction. A bright pixel whose raw variance sits just inside the floor has
    to be floored (tol = +inf) at every ``neff`` — before the fix the Bessel
    factor (up to 1.5× at neff≈3) inflated the variance *before* the floor test,
    lifting a low-coverage pixel out of the floor and re-enabling a spurious clip
    against cancellation noise."""
    m = np.array([[100.0]], dtype=np.float32)  # bright: m² = 1e4
    # Raw variance comfortably inside the floor (0.8× the threshold), yet Bessel
    # at neff=3 (×1.5) would push it to 1.2× — over the threshold — pre-fix.
    var_raw = 0.8 * _VAR_RESOLUTION_FACTOR * (100.0**2)
    m2 = (m.astype(np.float64) ** 2 + var_raw).astype(np.float32)
    for neff in (_MIN_REJECT_NEFF, 5.0, 100.0):
        wht = np.array([[neff]], dtype=np.float32)
        _, tol = _clip_tolerance(m, m2, wht, kappa=3.0)
        assert np.isinf(tol[0, 0]), f"floor must hold at neff={neff}"

    # Sanity: a variance well *above* the floor still yields a finite, positive
    # tolerance (the floor only disables clipping in the unresolved regime), and
    # that tolerance carries the Bessel inflation as intended.
    big_var = 100.0  # ≫ floor
    m2_big = (m.astype(np.float64) ** 2 + big_var).astype(np.float32)
    _, tol_lo = _clip_tolerance(m, m2_big, np.array([[3.0]], np.float32), kappa=3.0)
    _, tol_hi = _clip_tolerance(m, m2_big, np.array([[999.0]], np.float32), kappa=3.0)
    assert np.isfinite(tol_lo[0, 0]) and tol_lo[0, 0] > 0
    assert tol_lo[0, 0] > tol_hi[0, 0], "small-sample tol must be Bessel-widened"


def test_reject_gate_uses_frame_count_not_weight_when_the_drop_spreads():
    """When a frame's drop spreads across several output pixels (``scale > 1``, or
    the sub-pixel dither of any real stack at ``pixfrac < 1``), each frame deposits
    a *fractional* per-output-pixel weight, so the accumulated ``out_wht``
    understates the true frame count. The reject gate must key on the frame count
    (``self._count``), not ``out_wht`` — otherwise a low-coverage pixel hit by ≥3
    frames but carrying ``out_wht < 3`` has rejection silently disabled, and a
    satellite / plane trail on a mosaic edge survives into the master.

    Uses the recommended super-res config (``scale=2, pixfrac=0.8``), where one
    input pixel spreads over ~4 output pixels so a 4-frame output pixel carries
    ``out_wht ≈ 1`` — well under the ``_MIN_REJECT_NEFF = 3`` floor."""
    wcs = wcs_from_text(make_synth_wcs_text(width=40, height=40))
    stats = DrizzleStacker(wcs, (40, 40),
                           DrizzleParams(scale=2.0, pixfrac=0.8),
                           compute_stats=True)
    # Four aligned frames with real spread so the variance is well above the floor.
    for v in (100.0, 100.0, 100.0, 260.0):
        stats.add_frame(np.full((40, 40, 3), v, dtype=np.float32), wcs)

    cy, cx = 40, 40  # interior output pixel (canvas is 80×80 at scale 2)
    # The heart of the bug: the true frame count is 4, yet the spread weight sum
    # lands well under the _MIN_REJECT_NEFF = 3 floor.
    assert stats.frame_coverage[cy, cx] == 4
    assert stats.coverage[cy, cx, 0] < _MIN_REJECT_NEFF

    _mean, tol = stats.clip_reference(kappa=3.0)
    # Post-fix: rejection is enabled here (finite tol) because 4 frames ≥ 3.
    # Fail-before: neff = out_wht ≈ 1 < 3 → tol = +inf (rejection wrongly off).
    assert np.isfinite(tol[cy, cx, 0])


def test_clip_tolerance_neff_override_gates_on_the_supplied_count():
    """Unit-level: with a low ``wht`` but a supplied frame-count ``neff ≥`` the
    floor, ``_clip_tolerance`` enables rejection; without the override the same
    low ``wht`` disables it. Pins the ``neff`` plumbing independently of drizzle."""
    m = np.array([[130.0]], dtype=np.float32)
    m2 = np.array([[130.0**2 + 400.0]], dtype=np.float32)  # resolved variance
    wht = np.array([[2.56]], dtype=np.float32)  # 4 frames at pixfrac 0.8
    # Weight-as-count (the old behaviour): under the floor → never reject.
    _, tol_wht = _clip_tolerance(m, m2, wht, kappa=3.0)
    assert np.isinf(tol_wht[0, 0])
    # True frame count as neff: at/above the floor → rejection enabled.
    _, tol_cnt = _clip_tolerance(m, m2, wht, kappa=3.0,
                                 neff=np.array([[4]], dtype=np.uint32))
    assert np.isfinite(tol_cnt[0, 0]) and tol_cnt[0, 0] > 0


def _build_project(tmp_path, frames_spec) -> Project:
    """``frames_spec``: list of dicts passed to write_seestar_fits + wcs shift."""
    proj = Project.create(tmp_path / "p", name="reject_test")
    raws = tmp_path / "raws"
    raws.mkdir()
    for i, spec in enumerate(frames_spec):
        shift = spec.pop("shift", (0.0, 0.0))
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, star_shift=shift, **spec,
        )
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=make_synth_wcs_text(crpix_shift=shift),
            ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


def _run(proj, **overrides) -> np.ndarray:
    from astropy.io import fits

    opts = dict(
        drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
        background_flatten=False, suppress_hot_pixels=False,
        max_workers=2, output_name="out",
    )
    opts.update(overrides)
    result = run_stack(proj, StackOptions(**opts))
    with fits.open(result.fits_path) as hdul:
        return np.asarray(hdul[0].data, dtype=np.float32)  # (3, H, W)


def test_e2e_satellite_trail_rejected(tmp_path):
    """One streaked sub among 16: without rejection the trail shows in the
    stack; with rejection it vanishes into the clean sky."""
    spec = [
        {"seed": 7, "noise_seed": 100 + i, "n_stars": 10, "streak": (i == 8)}
        for i in range(16)
    ]
    imgs = {}
    for reject in (False, True):
        proj = _build_project(tmp_path / f"r_{reject}", [dict(s) for s in spec])
        try:
            imgs[reject] = _run(proj, drizzle_reject=reject, output_name="trail")
        finally:
            proj.close()

    # The synth streak runs along y = x + 10. Compare each trail pixel with a
    # parallel off-trail pixel 30 columns to the right; median over samples is
    # robust to the handful of stars the trail crosses.
    ts = list(range(60, 240, 12))
    deltas = {
        k: np.median([
            img[1, 30 + t, 20 + t] - img[1, 30 + t, 50 + t] for t in ts
        ])
        for k, img in imgs.items()
    }
    assert deltas[False] > 150.0, f"trail should contaminate the plain drizzle, got {deltas[False]}"
    assert abs(deltas[True]) < 60.0, f"trail should be rejected, residual {deltas[True]}"
    # Rejection must not punch coverage holes: no new NaNs in the interior.
    interior_on = imgs[True][1, 20:300, 20:460]
    interior_off = imgs[False][1, 20:300, 20:460]
    assert np.isnan(interior_on).sum() <= np.isnan(interior_off).sum()


def test_e2e_star_cores_survive_dithered_reject(tmp_path):
    """THE safety property: on dithered subs of the same sky, rejection must
    not eat star cores. Because both the tested value and the pass-1 statistics
    are box-sampled raw pixels, the dither-phase spread widens σ exactly where
    PSF gradients are steep — bright-star photometry must match the unclipped
    drizzle to ~2%."""
    spec = [
        {
            "seed": 7, "noise_seed": 200 + i, "n_stars": 8,
            "shift": ((i % 4) * 0.25, ((i // 4) % 3) * 0.33),
        }
        for i in range(12)
    ]
    imgs = {}
    for reject in (False, True):
        proj = _build_project(tmp_path / f"d_{reject}", [dict(s) for s in spec])
        try:
            imgs[reject] = _run(
                proj, drizzle_reject=reject,
                drizzle_scale=1.5, drizzle_pixfrac=0.8, output_name="dither",
            )
        finally:
            proj.close()

    ref = imgs[False][1]
    got = imgs[True][1]
    # Locate the brightest star in the unclipped stack (away from edges).
    inner = np.nan_to_num(ref[20:-20, 20:-20], nan=0.0)
    iy, ix = np.unravel_index(np.argmax(inner), inner.shape)
    cy, cx = iy + 20, ix + 20
    ap_ref = np.nansum(ref[cy - 5:cy + 6, cx - 5:cx + 6])
    ap_got = np.nansum(got[cy - 5:cy + 6, cx - 5:cx + 6])
    assert ap_got == pytest.approx(ap_ref, rel=0.02), "star aperture flux changed"
    assert got[cy, cx] == pytest.approx(ref[cy, cx], rel=0.02), "star peak clipped"


def test_e2e_drizzle_reject_stamps_rejection_provenance(tmp_path):
    """A real drizzle-reject stack records how much it clipped in the FITS
    header (REJMODE/REJFRAC/REJNREJ/REJNTOT), so the run …/info endpoint and the
    History trust line can surface it — data-driven, like the κ-σ path. A plain
    drizzle (no rejection) stamps nothing."""
    from astropy.io import fits

    spec = [
        {"seed": 7, "noise_seed": 400 + i, "n_stars": 10, "streak": (i == 8)}
        for i in range(16)
    ]

    proj = _build_project(tmp_path / "prov_on", [dict(s) for s in spec])
    try:
        res = run_stack(proj, StackOptions(
            drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
            drizzle_reject=True, background_flatten=False,
            suppress_hot_pixels=False, max_workers=2, output_name="prov",
        ))
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
    finally:
        proj.close()

    assert hdr["REJMODE"] == "drizzle-reject"
    assert hdr["REJNTOT"] > 0
    assert hdr["REJNREJ"] >= 0
    # A single streaked sub among 16 clean ones: the clip fires but only on a
    # tiny fraction of samples (the trail), never a huge share.
    assert 0.0 <= hdr["REJFRAC"] < 0.2
    assert hdr["REJFRAC"] == pytest.approx(hdr["REJNREJ"] / hdr["REJNTOT"], rel=1e-3)

    # Plain single-pass drizzle stamps no rejection provenance.
    proj2 = _build_project(tmp_path / "prov_off", [dict(s) for s in spec])
    try:
        res2 = run_stack(proj2, StackOptions(
            drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
            drizzle_reject=False, background_flatten=False,
            suppress_hot_pixels=False, max_workers=2, output_name="prov2",
        ))
        with fits.open(res2.fits_path) as hdul:
            assert "REJMODE" not in hdul[0].header
    finally:
        proj2.close()


def test_e2e_reject_skipped_below_four_frames(tmp_path):
    """The n>=4 gate mirrors the standard sigma-clip path: with 3 frames the
    request is honoured by simply not rejecting (and not failing)."""
    spec = [{"seed": 7, "noise_seed": 300 + i, "n_stars": 6} for i in range(3)]
    imgs = {}
    for reject in (False, True):
        proj = _build_project(tmp_path / f"few_{reject}", [dict(s) for s in spec])
        try:
            imgs[reject] = _run(proj, drizzle_reject=reject, output_name="few")
        finally:
            proj.close()
    np.testing.assert_allclose(
        imgs[True][:, 20:-20, 20:-20], imgs[False][:, 20:-20, 20:-20],
        rtol=1e-4, atol=0.5,
    )


# --- affordability of an UNATTENDED rejection ----------------------------------
#
# The walk-away chain turns ``drizzle_reject`` on for the user (``_stack_target``,
# alongside ``auto_reject``). The pass holds ~7 full-canvas planes against the
# single pass's 4, so charging it unconditionally can push a large drizzled mosaic
# — the owner's own setup — past the memory guard and turn a target that produced a
# picture yesterday into a hard MemoryError refusal, unattended, with nobody there
# to lower the drizzle scale. ``_afford_drizzle_reject`` declines a rejection the
# budget can't take, so the run proceeds exactly as it did before the pass was ever
# auto-enabled. A run somebody is *watching* still refuses loudly.
#
# The posture is ``options.unattended`` (v0.281.0), not ``auto_reject``: the Stack
# form seeds ``auto_reject=True`` for a never-configured target, so reading it as
# "unattended" quietly degraded a beginner who was sitting right there.


def _budget_between_passes_gb(shape, scale=1.0):
    """A budget (GB) that fits single-pass drizzle on ``shape`` but not two-pass."""
    from seestack.stack import stacker as st

    single, _ = st._estimate_peak_bytes(shape, drizzle=True, drizzle_scale=scale,
                                        drizzle_reject=False)
    two, _ = st._estimate_peak_bytes(shape, drizzle=True, drizzle_scale=scale,
                                     drizzle_reject=True)
    assert single < two
    return (single + two) / 2 / 1e9


def test_afford_declines_an_unattended_reject_that_busts_the_budget():
    from seestack.stack import stacker as st

    shape = (2000, 3000)
    auto = StackOptions(drizzle=True, drizzle_reject=True, auto_reject=True,
                        unattended=True)
    gb = _budget_between_passes_gb(shape)
    assert st._afford_drizzle_reject(auto, 20, shape, gb) is False
    # Room for both passes → the rejection is taken.
    assert st._afford_drizzle_reject(auto, 20, shape, gb * 4) is True


def test_afford_passes_a_watched_run_through_to_the_loud_refusal():
    """A run somebody is watching is never quietly downgraded — they can act on
    the fix the refusal names."""
    from seestack.stack import stacker as st

    shape = (2000, 3000)
    explicit = StackOptions(drizzle=True, drizzle_reject=True, auto_reject=False)
    gb = _budget_between_passes_gb(shape)
    assert st._afford_drizzle_reject(explicit, 20, shape, gb) is True
    with pytest.raises(MemoryError, match="outlier rejection"):
        st._guard_stack_memory(shape, drizzle=True, drizzle_scale=1.0,
                               drizzle_reject=True, memory_budget_gb=gb)


def test_afford_reads_the_posture_not_auto_reject():
    """The divergence this closes: ``get_stack_defaults`` seeds ``auto_reject=True``
    into the *manual* Stack form for a never-configured target, so a beginner
    sitting right there posts it. Reading ``auto_reject`` as "nobody is watching"
    silently dropped the rejection they explicitly ticked, instead of handing them
    the one-line fix. The posture — and only the posture — decides."""
    from seestack.stack import stacker as st

    shape = (2000, 3000)
    gb = _budget_between_passes_gb(shape)
    watched = StackOptions(drizzle=True, drizzle_reject=True, auto_reject=True)
    assert watched.unattended is False           # the form never sets it
    assert st._afford_drizzle_reject(watched, 20, shape, gb) is True
    # …and the walk-away run, which sets no rejection preference of its own
    # beyond what the chain merged, is the one that degrades.
    walk_away = replace(watched, unattended=True)
    assert st._afford_drizzle_reject(walk_away, 20, shape, gb) is False


def test_afford_never_hides_a_canvas_that_does_not_fit_either():
    """Only the extra rejection planes are forgiven. When even the single pass is
    over budget the guard must still refuse — with the numbers of the run that
    would actually be attempted."""
    from seestack.stack import stacker as st

    shape = (2000, 3000)
    auto = StackOptions(drizzle=True, drizzle_reject=True, unattended=True)
    single, _ = st._estimate_peak_bytes(shape, drizzle=True, drizzle_scale=1.0,
                                        drizzle_reject=False)
    tiny_gb = single / 2 / 1e9
    assert st._afford_drizzle_reject(auto, 20, shape, tiny_gb) is False
    with pytest.raises(MemoryError, match="working memory") as exc:
        st._guard_stack_memory(shape, drizzle=True, drizzle_scale=1.0,
                               drizzle_reject=False, memory_budget_gb=tiny_gb)
    assert "outlier rejection" not in str(exc.value)


def test_afford_folds_in_the_frame_floor_and_the_off_case():
    from seestack.stack import stacker as st

    shape = (100, 100)
    auto = StackOptions(drizzle=True, drizzle_reject=True, unattended=True)
    assert st._afford_drizzle_reject(auto, 3, shape, 64.0) is False   # n < 4
    assert st._afford_drizzle_reject(auto, 4, shape, 64.0) is True
    off = StackOptions(drizzle=True, drizzle_reject=False, unattended=True)
    assert st._afford_drizzle_reject(off, 20, shape, 64.0) is False
    no_drizzle = StackOptions(drizzle=False, drizzle_reject=True, unattended=True)
    assert st._afford_drizzle_reject(no_drizzle, 20, shape, 64.0) is False


def test_e2e_unattended_stack_still_produces_a_picture_when_reject_wont_fit(tmp_path):
    """The bug this closes: a walk-away drizzled stack on a budget that fits the
    single pass but not the two-pass one must still produce its picture, not raise
    MemoryError — and must say in the header why it carries no REJMODE."""
    from astropy.io import fits

    from seestack.stack import stacker as st
    from seestack.stack.stacker import estimate_stack

    spec = [{"seed": 7, "noise_seed": 500 + i, "n_stars": 8} for i in range(8)]
    base = dict(drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
                background_flatten=False, suppress_hot_pixels=False,
                max_workers=2, output_name="afford")

    proj = _build_project(tmp_path / "afford", [dict(s) for s in spec])
    try:
        est = estimate_stack(proj, StackOptions(**base))
        gb = _budget_between_passes_gb((est.canvas_h, est.canvas_w))
        # A watched run on this budget is refused — that is today's behaviour and
        # it stays, because the user who submitted it can act on the advice. This
        # is the *manual Stack form* shape: the seeded ``auto_reject=True`` a
        # never-configured target posts must NOT buy it a silent degrade.
        with pytest.raises(MemoryError, match="outlier rejection"):
            run_stack(proj, StackOptions(drizzle_reject=True, auto_reject=True,
                                         **base),
                      memory_budget_gb=gb)
        # The unattended shape of the same request (as the walk-away chain sets
        # it) produces the picture instead.
        res = run_stack(
            proj, StackOptions(drizzle_reject=True, auto_reject=True,
                               unattended=True, **base),
            memory_budget_gb=gb)
        assert res.fits_path.exists()
        assert res.n_frames_used == 8
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
        assert "REJMODE" not in hdr          # the pass genuinely didn't run…
        assert hdr["DRZREJSK"] == "memory"   # …and the header says why
        # The pre-run estimate agrees with what the run did: no phantom warning
        # about planes the run would decline to allocate.
        est_auto = estimate_stack(
            proj, StackOptions(drizzle_reject=True, auto_reject=True,
                               unattended=True, **base),
            memory_budget_gb=gb)
        assert est_auto.would_exceed is False
        # …while the watched request's estimate still warns, matching its refusal
        # — so the Stack form's pre-submit warning and the run now agree for the
        # beginner whose form carries the seeded ``auto_reject``.
        est_explicit = estimate_stack(
            proj, StackOptions(drizzle_reject=True, auto_reject=True, **base),
            memory_budget_gb=gb)
        assert est_explicit.would_exceed is True
        # Sanity: the affordable budget really does run the pass.
        big = st._estimate_peak_bytes(
            (est.canvas_h, est.canvas_w), drizzle=True, drizzle_scale=1.0,
            drizzle_reject=True)[0] * 4 / 1e9
        res_ok = run_stack(
            proj, StackOptions(drizzle_reject=True, auto_reject=True,
                               unattended=True,
                               **{**base, "output_name": "afford_ok"}),
            memory_budget_gb=big)
        with fits.open(res_ok.fits_path) as hdul:
            assert hdul[0].header["REJMODE"] == "drizzle-reject"
            assert "DRZREJSK" not in hdul[0].header
    finally:
        proj.close()


def test_a_non_drizzle_run_carrying_drizzle_reject_is_left_alone(tmp_path):
    """A saved default can hold `drizzle_reject` with drizzle *off* — the Stack
    form hides the box, it doesn't clear the value. That combination has always
    been an inert no-op, and must stay one: the drizzle-affordability check must
    not fire on it at all, so there is no DRZREJSK card however tight the budget,
    and the ordinary rejection path is untouched."""
    from astropy.io import fits

    spec = [{"seed": 7, "noise_seed": 600 + i, "n_stars": 8} for i in range(8)]
    proj = _build_project(tmp_path / "nodrizzle", [dict(s) for s in spec])
    try:
        res = run_stack(proj, StackOptions(
            drizzle=False, drizzle_reject=True, auto_reject=True,
            unattended=True,
            background_flatten=False, suppress_hot_pixels=False,
            max_workers=2, output_name="nodz",
        ), memory_budget_gb=1.0)
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
        assert "DRZREJSK" not in hdr
        assert hdr["STACKER"] != "drizzle"
        assert hdr["REJMODE"]  # auto_reject still resolved to a real method
    finally:
        proj.close()


# --- an unattended run whose CANVAS won't fit ----------------------------------
#
# Declining the rejection pass above only frees its extra planes. When even the
# single pass's canvas busts the budget, the guard refuses the whole run. That is
# right for a watching user — the refusal names the one lever that would fit and
# they click it — but at 3 a.m. nobody reads it, so a target that made a picture
# yesterday just stops. On an unattended run the engine now takes the lever it
# already computed: a smaller super-resolution scale. A picture at ×1.3 beats no
# picture, and the header says what it did.


def _budget_between_scales_gb(shape, low, high):
    """A budget (GB) fitting single-pass drizzle at ``low`` but not at ``high``."""
    from seestack.stack import stacker as st

    lo, _ = st._estimate_peak_bytes(shape, drizzle=True, drizzle_scale=low,
                                    drizzle_reject=False)
    hi, _ = st._estimate_peak_bytes(shape, drizzle=True, drizzle_scale=high,
                                    drizzle_reject=False)
    assert lo < hi
    return (lo + hi) / 2 / 1e9


def test_e2e_unattended_stack_lowers_the_drizzle_scale_instead_of_refusing(tmp_path):
    """The gap this closes: an over-budget *canvas* on the walk-away path used to
    raise MemoryError with advice nobody was there to read, so the target silently
    stopped producing pictures. It must now produce one at the largest scale that
    fits — and a watched run must still get the actionable refusal."""
    from astropy.io import fits

    from seestack.stack.stacker import estimate_stack

    spec = [{"seed": 7, "noise_seed": 700 + i, "n_stars": 8} for i in range(6)]
    base = dict(drizzle=True, drizzle_pixfrac=1.0, background_flatten=False,
                suppress_hot_pixels=False, max_workers=2)

    proj = _build_project(tmp_path / "degrade", [dict(s) for s in spec])
    try:
        est = estimate_stack(proj, StackOptions(drizzle_scale=1.0, **base))
        shape = (est.canvas_h, est.canvas_w)
        gb = _budget_between_scales_gb(shape, 1.0, 2.0)

        # Watched: refused, with the concrete lever named. Unchanged behaviour.
        with pytest.raises(MemoryError, match="lower the drizzle scale"):
            run_stack(proj, StackOptions(drizzle_scale=2.0, output_name="watched",
                                         **base),
                      memory_budget_gb=gb)

        # Unattended: a picture instead, at a scale that fits.
        res = run_stack(
            proj, StackOptions(drizzle_scale=2.0, unattended=True,
                               output_name="walkaway", **base),
            memory_budget_gb=gb)
        assert res.fits_path.exists()
        assert res.n_frames_used == 6
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
            data = hdul[0].data
        applied = float(hdr["DRZSCLAD"])
        assert hdr["DRZSCLRQ"] == pytest.approx(2.0)   # what was asked for
        assert 1.0 <= applied < 2.0                    # …and what actually ran
        # The picture really is at the applied scale, not the requested one.
        assert data.shape[-2:] == (round(shape[0] * applied),
                                   round(shape[1] * applied))
        # …and it genuinely fits the budget it was degraded to fit.
        from seestack.stack import stacker as st
        need, _ = st._estimate_peak_bytes(shape, drizzle=True,
                                          drizzle_scale=applied,
                                          drizzle_reject=False)
        assert need <= gb * 1e9
        # The run record persists the scale that ran, so a later reprocess
        # rebuilds the same picture rather than re-hitting the same refusal.
        for run in proj.iter_stack_runs():
            if run.output_basename == "walkaway":
                import json as _json
                assert _json.loads(run.options_json)["drizzle_scale"] == applied
                break
        else:  # pragma: no cover — the run must be there
            raise AssertionError("no stack run recorded for the walk-away stack")
    finally:
        proj.close()


def test_a_run_that_fits_is_never_degraded_and_stamps_nothing(tmp_path):
    """The self-hiding half: on a healthy budget an unattended run must be
    byte-for-byte the run it is today — the requested scale, and no card."""
    from astropy.io import fits

    spec = [{"seed": 7, "noise_seed": 800 + i, "n_stars": 8} for i in range(6)]
    proj = _build_project(tmp_path / "fits_fine", [dict(s) for s in spec])
    try:
        res = run_stack(proj, StackOptions(
            drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
            unattended=True, background_flatten=False,
            suppress_hot_pixels=False, max_workers=2, output_name="fine",
        ), memory_budget_gb=64.0)
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
        assert "DRZSCLAD" not in hdr
        assert "DRZSCLRQ" not in hdr
    finally:
        proj.close()


def test_unattended_still_refuses_when_even_unity_scale_will_not_fit(tmp_path):
    """Only a canvas a *smaller scale* can rescue is degraded. When even ×1.0 is
    over budget there is no honest picture to make, so the guard must still refuse
    rather than quietly producing something the box cannot hold."""
    spec = [{"seed": 7, "noise_seed": 900 + i, "n_stars": 8} for i in range(4)]
    proj = _build_project(tmp_path / "hopeless", [dict(s) for s in spec])
    try:
        from seestack.stack.stacker import estimate_stack

        est = estimate_stack(proj, StackOptions(
            drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
            background_flatten=False, suppress_hot_pixels=False,
            max_workers=2, output_name="hopeless"))
        from seestack.stack import stacker as st
        unity, _ = st._estimate_peak_bytes((est.canvas_h, est.canvas_w),
                                           drizzle=True, drizzle_scale=1.0,
                                           drizzle_reject=False)
        with pytest.raises(MemoryError, match="working memory"):
            run_stack(proj, StackOptions(
                drizzle=True, drizzle_scale=1.5, drizzle_pixfrac=1.0,
                unattended=True, background_flatten=False,
                suppress_hot_pixels=False, max_workers=2,
                output_name="hopeless",
            ), memory_budget_gb=unity / 2 / 1e9)
    finally:
        proj.close()


def test_a_non_drizzle_unattended_run_is_never_rescaled(tmp_path):
    """The degrade is a drizzle-only lever. A non-drizzle unattended run over
    budget must still refuse (its fixes are different levers), and a healthy one
    must carry no card."""
    spec = [{"seed": 7, "noise_seed": 950 + i, "n_stars": 8} for i in range(4)]
    proj = _build_project(tmp_path / "nodz_unattended", [dict(s) for s in spec])
    try:
        from astropy.io import fits

        res = run_stack(proj, StackOptions(
            drizzle=False, unattended=True, background_flatten=False,
            suppress_hot_pixels=False, max_workers=2, output_name="plain",
        ), memory_budget_gb=64.0)
        with fits.open(res.fits_path) as hdul:
            assert "DRZSCLAD" not in hdul[0].header
        with pytest.raises(MemoryError, match="working memory"):
            run_stack(proj, StackOptions(
                drizzle=False, unattended=True, background_flatten=False,
                suppress_hot_pixels=False, max_workers=2, output_name="plain2",
            ), memory_budget_gb=0.000001)
    finally:
        proj.close()


def test_a_sub_that_blipped_in_the_statistics_pass_reads_as_recovered(
        tmp_path, monkeypatch):
    """Two-pass drizzle is the other place a frame can fail one pass and land in
    the picture on the next. Its error line must say so, exactly as the κ-σ
    two-pass path's does (see ``tests/test_stack_two_pass_frame_count.py``)."""
    from seestack.stack.stacker import RECOVERED_ERROR_SUFFIX

    spec = [{"seed": 3, "noise_seed": 400 + i, "n_stars": 10} for i in range(6)]
    proj = _build_project(tmp_path / "recovered", [dict(s) for s in spec])
    try:
        real_add = DrizzleStacker.add_frame
        seen = {"stats": 0}

        def flaky(self, rgb, in_wcs, **kw):
            # ``_sq_drizzlers`` is only built for the statistics pass, so this
            # blips exactly one frame on pass 1 and leaves pass 2 alone.
            if self._sq_drizzlers is not None:
                seen["stats"] += 1
                if seen["stats"] == 1:
                    raise RuntimeError("transient read error")
            return real_add(self, rgb, in_wcs, **kw)

        monkeypatch.setattr(DrizzleStacker, "add_frame", flaky)
        res = run_stack(proj, StackOptions(
            drizzle=True, drizzle_reject=True, drizzle_scale=1.0,
            drizzle_pixfrac=1.0, background_flatten=False,
            suppress_hot_pixels=False, max_workers=1, output_name="recovered",
        ))
        # Every frame was deposited by pass 2, so every frame is in the picture.
        assert res.n_frames_used == 6
        assert len(res.errors) == 1, res.errors
        assert "transient read error" in res.errors[0]
        assert res.errors[0].endswith(RECOVERED_ERROR_SUFFIX)
        # …and the counted form of the same truth, which is what actually
        # reaches a screen: one sub hit a read error, and it recovered.
        assert res.n_read_errors == 1
        assert res.n_read_recovered == 1
    finally:
        proj.close()


def test_drizzle_rejection_is_blind_to_a_lone_outlier_below_kappa_min_frames():
    """The measurement behind the ``rejection_blind`` note's drizzle branch.

    Two-pass drizzle rejection *dispatches* from 4 frames, and until v0.340.0
    that dispatch gate was what ``rejection_reach`` reported as the count at
    which it could remove something. It is the same κ·σ clip as the non-drizzle
    pass, against statistics that still contain the outlier, so the honest bound
    is :func:`kappa_min_frames` — and this sweep is where that stops being an
    argument: one sub carries a bright block, the rest are clean, and the block
    comes out **fully diluted** (the naive no-rejection average, to a part in
    1e-3) at every depth up to 10, then vanishes at 11.

    That is the owner's case, not a corner: a mosaic panel rarely holds 11 subs,
    the panels are what a pixel sees, and the owner drizzles mosaics. The run
    still stamps ``REJMODE = drizzle-reject`` and ``REJFRAC 0.0`` throughout,
    which is exactly the "it ran and your data was clean" reading the note now
    contradicts.
    """
    from seestack.stack.stacker import kappa_min_frames

    need = kappa_min_frames(3.0)
    assert need == 11
    wcs = _wcs()
    for n in (4, 6, 8, 10, need, need + 1):
        clean = np.full((80, 100, 3), 100.0, dtype=np.float32)
        dirty = clean.copy()
        dirty[30:40, 40:60, :] = 5000.0
        frames = [clean.copy() for _ in range(n - 1)] + [dirty]
        got = _stack_with_clip(frames, wcs, reject=True)[35, 50, 1]
        diluted = ((n - 1) * 100.0 + 5000.0) / n
        if n < need:
            assert got == pytest.approx(diluted, rel=1e-3), (
                f"{n} subs: the clip removed something it cannot remove")
        else:
            assert got == pytest.approx(100.0, rel=1e-3), (
                f"{n} subs: the clip should have dropped the block by now")
