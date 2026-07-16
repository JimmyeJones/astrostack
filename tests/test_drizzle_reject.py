"""Two-pass drizzle outlier rejection (``StackOptions.drizzle_reject``).

Single-pass drizzle keeps every contribution, so a satellite/plane trail or
cosmic ray in one sub lands permanently in the drizzled output. The two-pass
mode builds per-output-pixel contribution statistics first (value and value²
drizzled under the same weights), then re-drizzles with contributions outside
``mean ± κ·σ`` zero-weighted. These tests pin down the astro-correctness
properties: trails are rejected, star cores are NOT eaten under dithering,
low-coverage pixels are never clipped, and NaN/coverage semantics hold.
"""

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
