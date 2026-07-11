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


def test_scnr_average_removes_at_least_as_much_green_as_maximum():
    """Locks the 'Protect' modes' relative strength against tooltip drift.

    ``average`` caps green to ``0.5*(r+b)`` and ``maximum`` to ``max(r,b)`` — so
    when red≠blue the average cap is the *lower* one and removes *more* green: it
    is the STRONGER protection, ``maximum`` the GENTLER. The help text on the
    ``mode`` param must describe them that way round (it once had them reversed).
    """
    rgb = _rgb(0.2, 0.9, 0.4)  # green cast with unequal red/blue so the caps differ
    op = get_op("tone.scnr")
    avg = op.apply(rgb, {"amount": 1.0, "mode": "average"}, EditContext())
    mx = op.apply(rgb, {"amount": 1.0, "mode": "maximum"}, EditContext())
    # average caps green to 0.5*(0.2+0.4)=0.3; maximum to max(0.2,0.4)=0.4.
    assert np.allclose(avg[..., 1], 0.3, atol=1e-5)
    assert np.allclose(mx[..., 1], 0.4, atol=1e-5)
    # So 'average' leaves *less* green behind — it is the stronger effect.
    assert float(avg[..., 1].mean()) < float(mx[..., 1].mean())
    # And the tooltip must label them accordingly (guards against re-reversal).
    help_text = next(p.help for p in op.params if p.key == "mode")
    assert "average (stronger)" in help_text and "maximum (gentler)" in help_text


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


# ---- tone.neutralize_background --------------------------------------------

def _cast_sky_image(r: float, g: float, b: float,
                    h: int = 40, w: int = 40) -> np.ndarray:
    """A dim, colour-cast sky background with a small bright target block.

    The bright block sits well above the luminance median so it's *excluded* from
    the sky population — a neutralise must balance the sky, not the target."""
    img = _rgb(r, g, b, h, w)
    img[4:10, 4:10, :] = 0.7  # bright target/star region (neutral, above the sky)
    return img


def test_neutralize_background_balances_sky_to_neutral():
    from seestack.edit.histogram import measure_sky_cast
    rgb = _cast_sky_image(0.20, 0.24, 0.20)  # green sky cast
    assert measure_sky_cast(rgb)["cast"] == "green"  # cast present before
    out = get_op("tone.neutralize_background").apply(rgb, {"strength": 1.0}, EditContext())
    assert measure_sky_cast(out)["neutral"] is True  # neutral after
    # Every gain is <= 1 (targets the darkest channel), so no channel brightens
    # past its input — the darkest channels (r, b) are untouched, green darkens.
    assert np.all(out[..., 0] <= rgb[..., 0] + 1e-6)
    assert np.all(out[..., 1] <= rgb[..., 1] + 1e-6)
    assert np.all(out[..., 2] <= rgb[..., 2] + 1e-6)


def test_neutralize_background_strength_scales_the_correction():
    from seestack.edit.histogram import sky_channel_medians
    rgb = _cast_sky_image(0.20, 0.24, 0.20)
    half = get_op("tone.neutralize_background").apply(rgb, {"strength": 0.5}, EditContext())
    meds = sky_channel_medians(half)
    # Half strength moves green halfway from 0.24 toward the 0.20 minimum (~0.22).
    assert abs(meds[1] - 0.22) < 5e-3
    # strength 0 is an identity (no correction at all).
    noop = get_op("tone.neutralize_background").apply(rgb, {"strength": 0.0}, EditContext())
    assert np.allclose(noop, rgb, atol=1e-6)


def test_neutralize_background_preserves_nan_gaps():
    rgb = _with_nan_border(_cast_sky_image(0.20, 0.24, 0.20))
    out = get_op("tone.neutralize_background").apply(rgb, {"strength": 1.0}, EditContext())
    assert np.all(np.isnan(out[:3, :, :]))
    assert np.all(np.isfinite(out[3:, :, :]))


def test_neutralize_background_noop_on_already_neutral_sky():
    rgb = _cast_sky_image(0.21, 0.21, 0.21)  # already neutral
    out = get_op("tone.neutralize_background").apply(rgb, {"strength": 1.0}, EditContext())
    assert np.allclose(out, rgb, atol=1e-6)


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


def _dim_ramp(h: int = 60, w: int = 60) -> np.ndarray:
    """A dim grayscale ramp (p50 ≈ 0.125 < the 0.25 target) so the data-driven
    auto-contrast curve has a real midtone to lift."""
    ramp = np.linspace(0.05, 0.20, h, dtype=np.float32)
    plane = np.repeat(ramp[:, None], w, axis=1)
    return np.stack([plane, plane, plane], axis=-1)


def test_curves_auto_lifts_midtones_from_identity():
    """With auto=True and the untouched identity points, the Curves op derives a
    gentle data-driven contrast curve from its (display-space) input — lifting the
    midtones above the plain identity while keeping the image finite and in range."""
    rgb = _dim_ramp()
    op = get_op("tone.curves")
    identity = op.apply(rgb, {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": False}, EditContext())
    auto = op.apply(rgb, {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, EditContext())
    assert np.all(np.isfinite(auto))
    assert auto.mean() > identity.mean() + 1e-3          # a real midtone lift
    assert float(auto.min()) == pytest.approx(float(rgb.min()), abs=0.02)  # sky floor pinned
    assert float(auto.max()) <= 1.0 + 1e-6               # highlights not blown out of range


def test_curves_auto_falls_back_to_fixed_scurve_when_no_suggestion():
    """On an already-bright image suggest_tone_curve declines (nothing to lift), so
    auto must fall back to the fixed gentle S-curve, not silently no-op."""
    from seestack.edit.ops.tone import _AUTO_CONTRAST_FALLBACK

    rgb = _rgb(0.6, 0.6, 0.6)
    op = get_op("tone.curves")
    auto = op.apply(rgb, {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, EditContext())
    fixed = op.apply(rgb, {"points": _AUTO_CONTRAST_FALLBACK, "auto": False}, EditContext())
    assert np.allclose(auto, fixed, atol=1e-4)
    assert not np.allclose(auto, rgb, atol=1e-3)          # the fallback actually shaped it


def test_curves_auto_ignored_when_points_manually_set():
    """A hand-edited (non-identity) curve always wins — toggling auto must never
    discard manual work by overriding it with the data-driven curve."""
    rgb = _dim_ramp()
    op = get_op("tone.curves")
    manual = [[0.0, 0.0], [0.5, 0.9], [1.0, 1.0]]
    with_auto = op.apply(rgb, {"points": manual, "auto": True}, EditContext())
    without_auto = op.apply(rgb, {"points": manual, "auto": False}, EditContext())
    assert np.allclose(with_auto, without_auto, atol=1e-5)


def test_curves_auto_preserves_nan_gaps():
    rgb = _with_nan_border(_dim_ramp())
    out = get_op("tone.curves").apply(
        rgb, {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, EditContext())
    assert np.all(np.isnan(out[:3, :, :]))
    assert np.all(np.isfinite(out[3:, :, :]))


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
