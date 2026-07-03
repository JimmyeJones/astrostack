"""Direct pixel-transform tests for the tone/colour editor ops.

seestack/edit/ops/tone.py's ops (SCNR, saturation, white balance, curves,
levels) had no dedicated pixel-level test — the engine test exercises a full
recipe end-to-end, but not each op's own forwarding + NaN handling. Each op
must (a) do the transform its params ask for and (b) leave uncovered NaN gaps
(mosaic borders / failed-solve regions) as NaN, never fabricating a zero wedge
that downstream reductions would drag toward black.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.edit.registry import EditContext, get_op


def _rgb(r: float, g: float, b: float, h: int = 12, w: int = 12) -> np.ndarray:
    out = np.empty((h, w, 3), dtype=np.float32)
    out[..., 0], out[..., 1], out[..., 2] = r, g, b
    return out


def _with_nan_border(rgb: np.ndarray, rows: int = 3) -> np.ndarray:
    out = rgb.copy()
    out[:rows, :, :] = np.nan
    return out


# ---- tone.scnr -------------------------------------------------------------

def test_scnr_caps_excess_green_to_the_rb_neutral():
    rgb = _rgb(0.3, 0.8, 0.3)  # strong green cast (g >> 0.5*(r+b)=0.3)
    op = get_op("tone.scnr")
    out = op.apply(rgb, {"amount": 1.0}, EditContext())
    # amount=1 fully caps green down to the red/blue neutral.
    assert np.allclose(out[..., 1], 0.3, atol=1e-5)
    # Red and blue are untouched.
    assert np.allclose(out[..., 0], 0.3) and np.allclose(out[..., 2], 0.3)


def test_scnr_never_adds_green():
    rgb = _rgb(0.6, 0.2, 0.6)  # green already below neutral — SCNR must not lift it
    op = get_op("tone.scnr")
    out = op.apply(rgb, {"amount": 1.0}, EditContext())
    assert np.allclose(out[..., 1], 0.2, atol=1e-5)


def test_scnr_preserves_nan_gaps():
    rgb = _with_nan_border(_rgb(0.3, 0.8, 0.3))
    out = get_op("tone.scnr").apply(rgb, {"amount": 0.7}, EditContext())
    assert np.all(np.isnan(out[:3, :, :]))
    assert np.all(np.isfinite(out[3:, :, :]))


# ---- tone.saturation -------------------------------------------------------

def test_saturation_boosts_channel_spread_around_luminance():
    rgb = _rgb(0.2, 0.5, 0.8)
    op = get_op("tone.saturation")
    boosted = op.apply(rgb, {"amount": 2.0}, EditContext())
    # A >1 amount pushes each channel further from the shared luminance.
    lum = 0.2125 * 0.2 + 0.7154 * 0.5 + 0.0721 * 0.8
    assert boosted[0, 0, 0] < 0.2  # below-lum channel pulled down
    assert boosted[0, 0, 2] > 0.8 or np.isclose(boosted[0, 0, 2], 1.0)  # above-lum up (clipped)
    # A neutral amount of 1.0 is an identity.
    ident = op.apply(rgb, {"amount": 1.0}, EditContext())
    assert np.allclose(ident, rgb, atol=1e-5)
    assert lum > 0  # sanity


def test_saturation_preserves_nan_gaps():
    rgb = _with_nan_border(_rgb(0.2, 0.5, 0.8))
    out = get_op("tone.saturation").apply(rgb, {"amount": 1.5}, EditContext())
    assert np.all(np.isnan(out[:3, :, :]))
    assert np.all(np.isfinite(out[3:, :, :]))


# ---- tone.white_balance ----------------------------------------------------

def test_white_balance_applies_per_channel_gain():
    rgb = _rgb(0.4, 0.4, 0.4)
    out = get_op("tone.white_balance").apply(rgb, {"r": 1.5, "g": 1.0, "b": 0.5}, EditContext())
    assert np.allclose(out[..., 0], 0.6, atol=1e-5)
    assert np.allclose(out[..., 1], 0.4, atol=1e-5)
    assert np.allclose(out[..., 2], 0.2, atol=1e-5)


def test_white_balance_preserves_nan_gaps():
    rgb = _with_nan_border(_rgb(0.4, 0.4, 0.4))
    out = get_op("tone.white_balance").apply(rgb, {"r": 1.2, "g": 1.0, "b": 0.9}, EditContext())
    assert np.all(np.isnan(out[:3, :, :]))
    assert np.all(np.isfinite(out[3:, :, :]))


# ---- tone.curves / tone.levels ---------------------------------------------

def test_curves_identity_default_is_noop_and_keeps_nan():
    rgb = _with_nan_border(_rgb(0.3, 0.5, 0.7))
    out = get_op("tone.curves").apply(rgb, {"points": [[0.0, 0.0], [1.0, 1.0]]}, EditContext())
    assert np.all(np.isnan(out[:3, :, :]))
    assert np.allclose(out[3:, :, :], rgb[3:, :, :], atol=1e-3)


def test_curves_lifts_midtones():
    rgb = _rgb(0.5, 0.5, 0.5)
    # A curve that maps 0.5 -> 0.7 must brighten the midtone.
    out = get_op("tone.curves").apply(
        rgb, {"points": [[0.0, 0.0], [0.5, 0.7], [1.0, 1.0]]}, EditContext())
    assert np.all(out[..., 0] > 0.5)


def test_curves_degenerate_single_point_is_identity_not_blank():
    """A one-point (or all-equal-x) curve can't define a mapping — np.interp would
    return a constant and blank the image to a flat tone. A degenerate hand-built/
    preset recipe must be treated as identity, not silently destroy the picture."""
    rgb = _with_nan_border(_rgb(0.3, 0.5, 0.7))
    op = get_op("tone.curves")
    one_point = op.apply(rgb, {"points": [[0.5, 0.5]]}, EditContext())
    flat_x = op.apply(rgb, {"points": [[0.5, 0.1], [0.5, 0.9]]}, EditContext())
    for out in (one_point, flat_x):
        assert np.all(np.isnan(out[:3, :, :]))                       # NaN border kept
        assert np.allclose(out[3:, :, :], rgb[3:, :, :], atol=1e-3)  # covered = unchanged


def test_levels_default_is_noop_and_gamma_brightens():
    rgb = _rgb(0.4, 0.4, 0.4)
    op = get_op("tone.levels")
    ident = op.apply(rgb, {"black": 0.0, "white": 1.0, "gamma": 1.0}, EditContext())
    assert np.allclose(ident, rgb, atol=1e-5)
    brighter = op.apply(rgb, {"black": 0.0, "white": 1.0, "gamma": 2.0}, EditContext())
    assert np.all(brighter[..., 0] > 0.4)


def test_levels_preserves_nan_gaps():
    rgb = _with_nan_border(_rgb(0.4, 0.4, 0.4))
    out = get_op("tone.levels").apply(rgb, {"black": 0.1, "white": 0.9, "gamma": 1.2}, EditContext())
    assert np.all(np.isnan(out[:3, :, :]))
    assert np.all(np.isfinite(out[3:, :, :]))


def test_levels_degenerate_white_le_black_is_identity_not_binarised():
    """White at or below black collapses the range and would hard-threshold every
    pixel to pure black/white (a beginner can drag the independent sliders there).
    It must be treated as identity, not silently binarise the picture — and an
    uncovered NaN border must stay NaN."""
    rgb = _with_nan_border(_rgb(0.3, 0.5, 0.7))
    op = get_op("tone.levels")
    inverted = op.apply(rgb, {"black": 0.6, "white": 0.4}, EditContext())   # white < black
    equal = op.apply(rgb, {"black": 0.5, "white": 0.5}, EditContext())      # white == black
    for out in (inverted, equal):
        assert np.all(np.isnan(out[:3, :, :]))                       # NaN border kept
        assert np.allclose(out[3:, :, :], rgb[3:, :, :], atol=1e-5)  # covered = unchanged
