"""How the one-click Auto chain measures "how noisy is this stack?".

Everything Auto decides about grain — how much to denoise, how much to sharpen,
how hard to run the colour-blotch smoother, how much saturation to add — hangs
off the single ``sky_sigma`` number ``analyze_proxy`` reports. This file pins the
property that number must have: it measures **grain**, not **structure**.

Owner-reported regression (2026-07-30, S30, real data): a deep ~400-sub mosaic
that rendered clean on an older build came out with a "multicolour grid" keyed to
the panel seams. The old estimator was the MAD of the sky's *levels*, which
counts a mosaic's per-panel level/colour offsets (and any residual light-pollution
gradient) as if they were noise — so a genuinely clean mosaic read as one of the
noisiest images the app had seen and got the wide-kernel chroma smoothing at full
strength, smearing colour across the seams.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.presets import (
    _AUTO_CHROMA_MAX,
    _noise_fraction,
    analyze_proxy,
    auto_recipe,
)

H, W = 300, 600
_PANEL_OFFSETS = (0.0, 0.012, -0.008, 0.016)
_PANEL_CHROMA = (
    (0.000, 0.000, 0.000),
    (0.004, -0.002, 0.000),
    (-0.003, 0.001, 0.002),
    (0.002, 0.003, -0.004),
)


def _scene(
    sigma: float, *, seed: int = 0, mosaic: bool = False, gradient: float = 0.0,
    nan_border: bool = False,
) -> np.ndarray:
    """A realistic linear proxy: sky + a faint extended object + stars + noise.

    ``mosaic=True`` adds the thing that matters — small per-panel level and
    colour offsets, exactly what photometric matching leaves behind at a mosaic's
    seams. The *pixel noise* is identical either way, so any difference in the
    measured σ is the estimator reacting to structure.
    """
    rng = np.random.default_rng(seed)
    img = np.broadcast_to(
        np.array([0.10, 0.12, 0.09], dtype=np.float32), (H, W, 3),
    ).astype(np.float32).copy()
    yy, xx = np.mgrid[0:H, 0:W]
    obj = np.exp(-(((xx - W / 2) / 50.0) ** 2 + ((yy - H / 2) / 35.0) ** 2))
    img += (obj[..., None] * np.array([0.05, 0.03, 0.02])).astype(np.float32)
    for _ in range(150):
        cy, cx = int(rng.integers(8, H - 8)), int(rng.integers(8, W - 8))
        amp = float(rng.uniform(0.2, 0.9))
        gy, gx = np.mgrid[cy - 6:cy + 7, cx - 6:cx + 7]
        star = amp * np.exp(-(((gx - cx) / 1.6) ** 2 + ((gy - cy) / 1.6) ** 2))
        img[cy - 6:cy + 7, cx - 6:cx + 7] += star[..., None].astype(np.float32)
    img += rng.normal(0.0, sigma, img.shape).astype(np.float32)
    if gradient:
        img += (gradient * (xx / W))[..., None].astype(np.float32)
    if mosaic:
        pw = W // len(_PANEL_OFFSETS)
        for i, off in enumerate(_PANEL_OFFSETS):
            sl = slice(i * pw, (i + 1) * pw)
            img[:, sl] += off
            img[:, sl] += np.array(_PANEL_CHROMA[i], dtype=np.float32)
    if nan_border:
        img[:15, :] = np.nan
        img[-15:, :] = np.nan
    return img


@pytest.mark.parametrize("sigma", [0.004, 0.01, 0.02, 0.05, 0.09])
def test_sky_sigma_matches_the_old_level_mad_on_pure_noise(sigma):
    """Upgrade safety: on a structure-free frame the local estimator must report
    what the old level-MAD reported, or every constant calibrated against it
    (the crossfade band, the "noisy" verdict, the saturation term) silently
    changes meaning and ordinary single-field stacks render differently.
    """
    img = _scene(sigma, seed=3)

    # The old estimator, verbatim, for comparison.
    lum = img[..., :3].mean(axis=2)
    finite = lum[np.isfinite(lum)]
    lo, hi = float(np.percentile(finite, 0.5)), float(np.percentile(finite, 99.5))
    norm = np.clip((finite - lo) / (hi - lo), 0.0, 1.0)
    med = float(np.median(norm))
    sky = norm[norm <= med]
    old = float(1.4826 * np.median(np.abs(sky - np.median(sky))))

    new = analyze_proxy(img)["sky_sigma"]
    # Within 3 % at every σ. What difference remains is largest at the *cleanest*
    # end (2.2 % at σ = 0.004), and it is the old estimator reading slightly high
    # because the faint extended object's own structure lands in its level MAD —
    # i.e. the very effect being removed, just small here.
    assert new == pytest.approx(old, rel=0.03), f"{new=} {old=}"


def test_a_deep_mosaics_panel_offsets_are_not_counted_as_noise():
    """The regression itself: the same deep stack, laid out as a mosaic.

    Only per-panel level/colour offsets differ — the pixel noise is identical —
    so the measured σ must barely move. Before the fix it more than tripled.
    """
    single = analyze_proxy(_scene(0.004, seed=5))["sky_sigma"]
    mosaic = analyze_proxy(_scene(0.004, seed=5, mosaic=True))["sky_sigma"]
    assert mosaic == pytest.approx(single, rel=0.25), f"{mosaic=} {single=}"


def test_a_deep_mosaic_does_not_get_the_colour_smoother_at_all():
    """End to end: a clean mosaic's one-click Auto must not contain the
    wide-kernel ``detail.chroma_denoise`` op — the one that smeared colour across
    the owner's panel seams — nor lose its sharpening to a phantom noise read."""
    mosaic = _scene(0.004, seed=7, mosaic=True)
    a = analyze_proxy(mosaic)
    assert _noise_fraction(a["sky_sigma"]) == 0.0
    assert a["noisy"] is False

    ids = [o.id for o in auto_recipe(mosaic).ops]
    assert "detail.chroma_denoise" not in ids
    assert "detail.denoise" not in ids
    assert "detail.sharpen" in ids


def test_the_same_stack_gets_the_same_recipe_whether_or_not_it_is_a_mosaic():
    """The property behind the fix, stated whole.

    Panel offsets are a *layout* artefact, not a property of the data's quality,
    so laying the identical stack out as a mosaic must not change what Auto does
    to it. Before the fix the mosaic lost its sharpening entirely
    (``amount`` 0.5 → 0.0), had its colour boost cut back, and gained a full-
    strength colour smoother.
    """
    single = {o.id: o.params for o in auto_recipe(_scene(0.004, seed=7)).ops}
    mosaic = {o.id: o.params for o in auto_recipe(_scene(0.004, seed=7, mosaic=True)).ops}
    assert list(single) == list(mosaic)
    assert float(mosaic["detail.sharpen"]["amount"]) == pytest.approx(
        float(single["detail.sharpen"]["amount"]), rel=0.05)
    assert float(mosaic["tone.saturation"]["amount"]) == pytest.approx(
        float(single["tone.saturation"]["amount"]), rel=0.05)


def test_a_genuinely_noisy_mosaic_still_gets_denoised():
    """The fix must not swing the other way: a thin, noisy mosaic is still noisy,
    and still gets the denoise + colour smoothing it needs."""
    noisy = _scene(0.05, seed=11, mosaic=True)
    a = analyze_proxy(noisy)
    assert _noise_fraction(a["sky_sigma"]) > 0.9
    assert a["noisy"] is True

    ops = {o.id: o for o in auto_recipe(noisy).ops}
    assert "detail.denoise" in ops
    chroma = ops.get("detail.chroma_denoise")
    assert chroma is not None
    assert 0.0 < float(chroma.params["strength"]) <= _AUTO_CHROMA_MAX


def test_a_residual_light_pollution_gradient_is_not_counted_as_noise():
    """The same failure mode on a single field: a smooth gradient is structure,
    not grain, and must not conjure a denoise pass onto a clean stack."""
    flat = analyze_proxy(_scene(0.004, seed=13))["sky_sigma"]
    tilted = analyze_proxy(_scene(0.004, seed=13, gradient=0.08))["sky_sigma"]
    assert tilted == pytest.approx(flat, rel=0.25), f"{tilted=} {flat=}"
    assert _noise_fraction(tilted) == 0.0


def test_uncovered_mosaic_border_does_not_inflate_the_measurement():
    """A mosaic's ragged NaN border is "no coverage", never a noisy sky."""
    covered = analyze_proxy(_scene(0.004, seed=17, mosaic=True))["sky_sigma"]
    ragged = analyze_proxy(
        _scene(0.004, seed=17, mosaic=True, nan_border=True),
    )["sky_sigma"]
    assert ragged == pytest.approx(covered, rel=0.25)


def test_an_unmeasurable_image_still_reads_as_clean():
    """The 'can't tell' convention the rest of the auto chain relies on."""
    assert analyze_proxy(np.zeros((4, 4, 3), np.float32))["sky_sigma"] == 0.0
    assert analyze_proxy(np.full((40, 40, 3), 0.2, np.float32))["sky_sigma"] == 0.0
    all_nan = analyze_proxy(np.full((40, 40, 3), np.nan, np.float32))
    assert all_nan["sky_sigma"] == 0.0
    assert all_nan["noisy"] is False
