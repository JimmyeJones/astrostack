"""A master flat's own colour must not reach the finished picture.

``CalibrationMasters.load`` normalises a master flat by **one global mean** over
the whole raw Bayer mosaic — across the R, G and B sites together — so a flat
panel that was warmer or cooler than neutral divides a *constant per-channel
gain* into every calibrated light. (Siril's "equalize CFA" exists for exactly
this.) The question that matters for a live install is not whether the gain is
there — it is, exactly as injected — but whether it survives to the picture the
owner looks at.

It does not, and **two** independent steps of the one-click Auto recipe see to
that: ``tone.color_calibrate`` (gray-star) solves for precisely a per-channel
constant, and ``tone.stretch``'s per-channel STF normalises each channel's own
black/mid point. Measured on this file's scene at a deliberately extreme
R ×1.5 / B ×0.7 cast — linear alone: R/G −33.3 %, B/G +42.8 %; colour
calibration alone: 0.0 % / 0.0 %; the stretch alone: +0.1 % / −0.1 %. This file
pins that, because the day Auto stops normalising per channel is the day a
flat's cast becomes visible — and the failure would show up as "my picture went
red after I made flats", a long way from the code that caused it.

Measured end-to-end for the record (Builder 2026-08-07, full ``run_stack`` →
``auto_recipe`` → ``apply_recipe`` on synthetic Seestar subs, a flat carrying
R ×1.08 / B ×0.95 over a vignette): the stacked *linear* FITS carried the cast
verbatim — star R/G 0.9354 → 0.8645, B/G 0.9365 → 0.9868, i.e. the injected
1/1.08 and 1/0.95 — while the finished picture's sky came out R/G 1.0351 vs
1.0352 and B/G 1.0380 vs 1.0379 against the neutral-flat control. At a
deliberately extreme R ×1.5 / B ×0.7 the finished sky still landed within 0.2 %,
and within 0.5 % on a star-poor 5-star field.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.pipeline import apply_recipe
from seestack.edit.presets import auto_recipe

H, W = 240, 360


def _linear_stack(seed: int = 11) -> np.ndarray:
    """A neutral linear stack: grey sky, a faint extended object, stars, grain."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), 0.10, dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    obj = np.exp(-(((xx - W / 2) / 45.0) ** 2 + ((yy - H / 2) / 30.0) ** 2))
    img += (obj[..., None] * 0.04).astype(np.float32)
    for _ in range(120):
        cy, cx = int(rng.integers(8, H - 8)), int(rng.integers(8, W - 8))
        amp = float(rng.uniform(0.2, 0.9))
        gy, gx = np.mgrid[cy - 6:cy + 7, cx - 6:cx + 7]
        star = amp * np.exp(-(((gx - cx) / 1.6) ** 2 + ((gy - cy) / 1.6) ** 2))
        img[cy - 6:cy + 7, cx - 6:cx + 7] += star[..., None].astype(np.float32)
    img += rng.normal(0.0, 0.004, img.shape).astype(np.float32)
    return img


def _sky_colour(rgb: np.ndarray) -> tuple[float, float]:
    """``(R/G, B/G)`` over the mid-level pixels — the *sky's* colour, which is
    the honest check here: gray-star calibration neutralises star colour by
    construction, so measuring the stars would only restate its own definition."""
    lum = np.nanmean(rgb, axis=2)
    lo, hi = np.nanpercentile(lum, [20, 60])
    m = (lum >= lo) & (lum <= hi)
    chans = [float(np.nanmean(rgb[..., c][m])) for c in range(3)]
    return chans[0] / chans[1], chans[2] / chans[1]


def _auto(rgb: np.ndarray) -> np.ndarray:
    return apply_recipe(rgb, auto_recipe(rgb))


@pytest.mark.parametrize("r_gain,b_gain", [(1.08, 0.95), (1.5, 0.7)])
def test_a_flats_own_colour_does_not_reach_the_finished_picture(r_gain, b_gain):
    neutral = _linear_stack()
    # A globally-normalised flat divides a per-channel constant into every light,
    # which reaches the stack as exactly this: the linear image scaled per channel.
    tinted = (neutral * np.array([1.0 / r_gain, 1.0, 1.0 / b_gain],
                                 dtype=np.float32)).astype(np.float32)

    # The cast really is in the linear stack — otherwise the assertion below
    # would pass for the wrong reason.
    lin_neutral, lin_tinted = _sky_colour(neutral), _sky_colour(tinted)
    assert lin_tinted[0] == pytest.approx(lin_neutral[0] / r_gain, rel=1e-3)
    assert lin_tinted[1] == pytest.approx(lin_neutral[1] / b_gain, rel=1e-3)

    # ...and it is gone from the picture Auto produces.
    out_neutral, out_tinted = _sky_colour(_auto(neutral)), _sky_colour(_auto(tinted))
    assert out_tinted[0] == pytest.approx(out_neutral[0], rel=0.02), (
        f"R/G {out_tinted[0]:.4f} vs {out_neutral[0]:.4f}")
    assert out_tinted[1] == pytest.approx(out_neutral[1], rel=0.02), (
        f"B/G {out_tinted[1]:.4f} vs {out_neutral[1]:.4f}")


def test_auto_keeps_both_of_the_steps_that_neutralise_it():
    """Name the dependency out loud. The invariance above is not incidental — it
    holds because Auto normalises per channel, twice over. Lose both and the
    test above starts failing for a reason nobody would connect to flats."""
    ids = [o.id for o in auto_recipe(_linear_stack()).ops]
    assert "tone.color_calibrate" in ids, ids
    assert "tone.stretch" in ids, ids


def test_the_cast_really_is_in_the_linear_stack():
    """The other half of the claim: nothing *before* the editor removes it, so
    the linear master FITS a user downloads (and anything that reads it without
    a per-channel normalisation) does carry the flat's colour. Measured on the
    real chain too — a flat with R ×1.08 / B ×0.95 moved the stacked FITS's star
    R/G from 0.9354 to 0.8645, exactly 1/1.08."""
    from seestack.edit.recipe import Recipe

    neutral = _linear_stack()
    tinted = (neutral * np.array([1.0 / 1.5, 1.0, 1.0 / 0.7],
                                 dtype=np.float32)).astype(np.float32)
    # An empty recipe with the display auto-stretch off is the linear data itself.
    lin = _sky_colour(apply_recipe(neutral, Recipe(ops=[]), auto_stretch=False))
    cast = _sky_colour(apply_recipe(tinted, Recipe(ops=[]), auto_stretch=False))
    assert cast[0] < lin[0] * 0.75, (cast, lin)
    assert cast[1] > lin[1] * 1.30, (cast, lin)
