"""What `photometric_normalize` is, and isn't, worth on a **single field**.

v0.271.0 auto-enabled photometric normalization for a mosaic canvas, because a
panel shot through haze is dimmed multiplicatively and leaves a visible step
along the join — a *spatial* inconsistency the sky-only corrections cannot
touch. The obvious next question, filed as a backlog idea the day that shipped,
is whether the same pass should auto-enable on an ordinary **single-field**
target stacked across nights of mixed transparency, which is what the walk-away
chain builds constantly as a beginner revisits one object.

**Measured 2026-09-08, and the answer is no** — not because it hurts, but because
quality weighting is already doing nearly all of it. On a single field every
output pixel receives the *same* set of subs, so there is no spatial
inconsistency to fix; all normalization can change is the combine weighting, and
with the `1/s²` variance fold that is inverse-variance weighting, which the
`transparency_factor` in quality weighting already approximates. Star-core SNR,
8 subs, quality weighting **on** (the auto path):

| case | SNR change |
|---|---|
| 8 clear, nothing to correct | **+0.00 %** (bit-identical) |
| 6 clear + 2 hazy, ×0.8 signal — the ordinary case | **+0.16 %** |
| 4 clear + 4 hazy, ×0.8 | +0.39 % |
| 6 clear + 2 hazy, ×0.5 | +1.22 % |
| 4 clear + 4 hazy, ×0.5 — an extreme | +3.33 % |

With quality weighting *off* the same cases give +0.50 / +0.61 / +3.30 / +5.53 %,
i.e. the pass is doing real work — it is just work the auto chain has largely
already done. A default flip on the on-by-default hot path needs more than
+0.16 %, so the option stays off outside a mosaic and this file pins the two
claims the decision rests on.

**One fixture note, because it inverted the answer.** The first attempt hazed a
sub with `sky + (pixel - sky) * factor`, which scales the sky *noise* by the
factor too — noise rides on that same difference. Every hazy sub came out
proportionally quieter, so after gain-matching the frames had identical signal
*and* identical noise, the correct `1/s²` weight became the wrong weight, and the
run read as a **9.7 % SNR loss** that was entirely fixture. Haze attenuates the
source, not the sky glow behind it. `make_star_field` draws its noise from
`noise_seed` before it places a star, so the same call with `n_stars=0` is
exactly that frame's sky — and the difference is exactly its stars.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("photutils")
pytest.importorskip("PIL")
pytest.importorskip("tifffile")

from astropy.io import fits  # noqa: E402

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_star_field, make_synth_wcs_text, write_seestar_fits  # noqa: E402

W, H = 480, 320
PIXSCALE = 5.0
RA, DEC = 83.6, -5.4
CLEAR_SCORE = 5000.0


def _hazed(seed: int, noise_seed: int, n_stars: int, factor: float) -> np.ndarray:
    """A sub whose *stars* are dimmed to ``factor`` with its sky left alone."""
    kw = dict(width=W, height=H, seed=seed, noise_seed=noise_seed)
    full = make_star_field(n_stars=n_stars, **kw).astype(np.float64)
    sky = make_star_field(n_stars=0, **kw).astype(np.float64)
    return np.clip(sky + (full - sky) * factor, 0, 65535).astype(np.uint16)


def _single_field_project(tmp_path, n_clear: int, n_hazy: int,
                          haze: float) -> Project:
    """One pointing, one star pattern, independent per-sub noise; some subs hazy.

    The shared star pattern is what makes the comparison possible at all: the two
    populations differ *only* by the haze, so any change in the stacked result is
    the normalization and not a different patch of sky.
    """
    proj = Project.create(tmp_path / "p", name="mixed-transparency")
    raws = tmp_path / "raws"
    raws.mkdir()
    wcs = make_synth_wcs_text(width=W, height=H, ra_center_deg=RA,
                              dec_center_deg=DEC, pixscale_arcsec=PIXSCALE)
    for j in range(n_clear + n_hazy):
        hazy = j >= n_clear
        path = write_seestar_fits(
            raws / f"s{j:02d}.fit", add_wcs=True, seed=7, noise_seed=500 + j,
            n_stars=40, ra_center_deg=RA, dec_center_deg=DEC,
            pixscale_arcsec=PIXSCALE,
            data=(_hazed(7, 500 + j, 40, haze) if hazy else None),
        )
        fid = proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=W, height_px=H, bayer_pattern="RGGB", wcs_json=wcs,
            ra_center_deg=RA, dec_center_deg=DEC,
        ))
        # What QC measures: the median flux of the frame's brightest stars, so a
        # hazed sub scores proportionally lower.
        proj.update_frame(fid, fwhm_px=3.0, star_count=40,
                          transparency_score=CLEAR_SCORE * (haze if hazy else 1.0))
    return proj


def _stack(proj: Project, *, photometric: bool, name: str) -> np.ndarray:
    res = run_stack(proj, StackOptions(
        sigma_clip=True, sigma_kappa=3.0, quality_weighted=True,
        photometric_normalize=photometric, background_flatten=False,
        output_name=name,
    ))
    assert res.n_frames_used > 0
    return np.asarray(fits.getdata(str(res.fits_path)), dtype=np.float64)


def _star_snr(data: np.ndarray) -> float:
    """Star-core flux above the sky, over the sigma-clipped background sigma."""
    from astropy.stats import sigma_clipped_stats

    lum = np.nanmean(data, axis=0) if data.ndim == 3 else data
    vals = lum[np.isfinite(lum)]
    _, sky, sigma = sigma_clipped_stats(vals, sigma=3.0, maxiters=10)
    cores = vals[vals >= np.percentile(vals, 99.8)]
    assert sigma > 0
    return float(np.mean(cores) - sky) / float(sigma)


def test_a_uniform_transparency_single_field_is_left_bit_for_bit_alone(tmp_path):
    """Nothing to correct → nothing changes, to the last bit.

    This is the safety half of the measurement: whatever the option is worth on a
    mixed stack, turning it on where every sub was shot through the same air must
    not perturb the picture at all. Every scale lands at 1.0, so no pixel is
    divided and no combine weight carries a `1/s²`.
    """
    proj = _single_field_project(tmp_path, n_clear=6, n_hazy=0, haze=1.0)
    try:
        off = _stack(proj, photometric=False, name="off")
        on = _stack(proj, photometric=True, name="on")
    finally:
        proj.close()
    assert on.shape == off.shape
    np.testing.assert_array_equal(np.isnan(on), np.isnan(off))
    finite = ~np.isnan(off)
    np.testing.assert_array_equal(on[finite], off[finite])


def test_a_mixed_transparency_single_field_gains_only_a_little(tmp_path):
    """A hazy night among clear ones: normalization helps, but barely.

    Two claims, and the *decision* rests on both. It never hurts — the `1/s²`
    fold means gain-matching a hazy sub up cannot let its amplified noise into
    the mean at full weight. And the win is small on the path the owner actually
    runs, because quality weighting already down-weights that sub: measured at
    **+0.16 %** star-core SNR on this exact case (a quarter of the subs at ×0.8),
    which is why `photometric_normalize` stays off outside a mosaic rather than
    being auto-enabled the way v0.271.0 enabled it there.

    The assertion is deliberately a *direction*, not the number: a future change
    that makes the pass genuinely better should not fail a test, it should send
    whoever made it back to the table above to re-litigate the default.
    """
    proj = _single_field_project(tmp_path, n_clear=6, n_hazy=2, haze=0.8)
    try:
        off = _star_snr(_stack(proj, photometric=False, name="off"))
        on = _star_snr(_stack(proj, photometric=True, name="on"))
    finally:
        proj.close()
    assert on >= off, f"normalization must never cost SNR: {off:.1f} -> {on:.1f}"
    # …and it is not the several-times win a mosaic's panel step gets from it.
    assert on / off < 1.10, f"unexpectedly large gain ({100 * (on / off - 1):.2f} %)"
