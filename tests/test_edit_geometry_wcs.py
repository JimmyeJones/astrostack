"""The sky solution follows the editor's geometry ops onto the edited canvas.

An editor export used to be written with no WCS at all, so every edited picture
lost North-up, the scale bar, the compass and its object labels. Tone ops move no
pixels, so nothing was ever lost there; crop and resize move them in a way the
solution can follow exactly. These tests pin *both* halves against the real ops:
the pixel replay (:func:`geometry_pixel_steps`) is asserted to agree with what the
ops actually did to the image, and the rewritten WCS is asserted to put a real
star back at the sky position the source WCS gave it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth import make_synth_wcs_text  # noqa: E402

from seestack.edit.ops.geometry import (  # noqa: E402
    crop_bounds,
    geometry_pixel_steps,
    resize_shape,
)
from seestack.edit.recipe import recipe_from_dict  # noqa: E402
from seestack.edit.registry import EditContext, get_op  # noqa: E402
from seestack.io.wcs_io import wcs_from_text, wcs_text_after_pixel_steps  # noqa: E402

W, H = 480, 320
DOT_X, DOT_Y = 200.0, 160.0


def _dot_image(x: float = DOT_X, y: float = DOT_Y) -> np.ndarray:
    """A black frame with one tight Gaussian star at ``(x, y)``, so a flux-weighted
    centroid recovers its position to well under a pixel."""
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.exp(-(((xx - x) / 2.0) ** 2 + ((yy - y) / 2.0) ** 2)).astype(np.float32)
    return np.repeat(img[..., None], 3, axis=2)


def _centroid(rgb: np.ndarray) -> tuple[float, float]:
    m = np.nan_to_num(np.asarray(rgb, dtype=np.float64)[..., 0])
    h, w = m.shape
    total = m.sum()
    yy, xx = np.mgrid[0:h, 0:w]
    return float((m * xx).sum() / total), float((m * yy).sum() / total)


def _apply(op_id: str, rgb: np.ndarray, params: dict) -> np.ndarray:
    return get_op(op_id).apply(rgb, params, EditContext(is_proxy=False, proxy_scale=1.0))


def _sky(text: str, x: float, y: float) -> tuple[float, float]:
    wcs = wcs_from_text(text).celestial
    ra, dec = (float(v) for v in wcs.all_pix2world([[x, y]], 0)[0])
    return ra, dec


def _sep_arcsec(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Angular separation of two (RA, Dec) pairs in arcsec (small-angle, ample here)."""
    dec = np.radians((a[1] + b[1]) / 2.0)
    dra = (a[0] - b[0]) * np.cos(dec)
    return float(np.hypot(dra, a[1] - b[1]) * 3600.0)


# ---- the pixel replay agrees with the ops -------------------------------------

def test_a_tone_only_recipe_has_no_geometry_steps():
    recipe = recipe_from_dict({"ops": [{"id": "tone.stretch", "params": {}},
                                       {"id": "tone.saturation",
                                        "params": {"amount": 1.2}}]})
    assert geometry_pixel_steps(recipe, (H, W)) == []


def test_crop_step_matches_the_slice_the_op_actually_took():
    params = {"x0": 0.25, "x1": 0.75, "y0": 0.2, "y1": 0.8}
    recipe = recipe_from_dict({"ops": [{"id": "geometry.crop", "params": params}]})
    steps = geometry_pixel_steps(recipe, (H, W))
    x0, x1, y0, y1 = crop_bounds(H, W, params)
    assert steps == [("crop", x0, y0)]
    out = _apply("geometry.crop", _dot_image(), params)
    assert out.shape[:2] == (y1 - y0, x1 - x0)


def test_resize_step_matches_the_shape_the_op_actually_produced():
    params = {"scale": 0.5}
    recipe = recipe_from_dict({"ops": [{"id": "geometry.resize", "params": params}]})
    out = _apply("geometry.resize", _dot_image(), params)
    out_h, out_w = resize_shape(H, W, params)
    assert out.shape[:2] == (out_h, out_w)
    assert geometry_pixel_steps(recipe, (H, W)) == [("resize", W, H, out_w, out_h)]


def test_a_degenerate_crop_and_a_unit_resize_contribute_no_step():
    """The ops no-op on these, so the WCS must not move either."""
    recipe = recipe_from_dict({"ops": [
        {"id": "geometry.crop", "params": {"x0": 0.5, "x1": 0.5001,
                                           "y0": 0.0, "y1": 1.0}},
        {"id": "geometry.resize", "params": {"scale": 1.0}},
    ]})
    assert geometry_pixel_steps(recipe, (H, W)) == []


def test_a_disabled_geometry_op_is_ignored():
    recipe = recipe_from_dict({"ops": [{"id": "geometry.crop", "enabled": False,
                                        "params": {"x0": 0.1, "x1": 0.9,
                                                   "y0": 0.1, "y1": 0.9}}]})
    assert geometry_pixel_steps(recipe, (H, W)) == []


def test_an_active_rotate_gives_up_rather_than_returning_a_wrong_wcs():
    recipe = recipe_from_dict({"ops": [{"id": "geometry.rotate",
                                        "params": {"angle": 12.0}}]})
    assert geometry_pixel_steps(recipe, (H, W)) is None


def test_a_rotate_below_its_own_threshold_is_the_no_op_the_op_treats_it_as():
    """``_rotate`` returns the image untouched below 1e-3°, so the WCS is still
    exactly right — giving up there would drop a solution for nothing."""
    recipe = recipe_from_dict({"ops": [{"id": "geometry.rotate",
                                        "params": {"angle": 0.0}}]})
    assert geometry_pixel_steps(recipe, (H, W)) == []
    img = _dot_image()
    assert np.array_equal(_apply("geometry.rotate", img, {"angle": 0.0}), img)


# ---- the rewritten WCS puts the star back where it was ------------------------

def test_no_steps_returns_the_wcs_unchanged():
    text = make_synth_wcs_text(width=W, height=H)
    assert wcs_text_after_pixel_steps(text, []) == text


def test_an_unusable_wcs_stays_none():
    assert wcs_text_after_pixel_steps(None, []) is None
    assert wcs_text_after_pixel_steps("END", [("crop", 3, 4)]) is None


def test_a_cropped_star_keeps_its_sky_position():
    src = make_synth_wcs_text(width=W, height=H)
    params = {"x0": 0.25, "x1": 0.75, "y0": 0.2, "y1": 0.8}
    out = _apply("geometry.crop", _dot_image(), params)
    cx, cy = _centroid(out)

    steps = geometry_pixel_steps(
        recipe_from_dict({"ops": [{"id": "geometry.crop", "params": params}]}), (H, W))
    moved = wcs_text_after_pixel_steps(src, steps)
    assert moved is not None
    # A crop is a pure integer translation, so the star lands *exactly* back on
    # its own sky position; the bound is centroid noise, not slack. Dropping the
    # offset entirely would put it ~600" away.
    assert _sep_arcsec(_sky(moved, cx, cy), _sky(src, DOT_X, DOT_Y)) < 0.1


@pytest.mark.parametrize("scale", [0.5, 0.37, 2.0])
def test_a_resized_star_keeps_its_sky_position_and_the_scale_follows(scale):
    src = make_synth_wcs_text(width=W, height=H)
    params = {"scale": scale}
    out = _apply("geometry.resize", _dot_image(), params)
    cx, cy = _centroid(out)

    steps = geometry_pixel_steps(
        recipe_from_dict({"ops": [{"id": "geometry.resize", "params": params}]}), (H, W))
    moved = wcs_text_after_pixel_steps(src, steps)
    assert moved is not None
    # Measured 0.0004–0.28" (< 0.06 px). The bound is tight on purpose: resampling
    # the *other* plausible way — scale rather than scipy's corner-aligned
    # (n_in − 1)/(n_out − 1) — lands 1.6–5.5" out and must not pass here.
    assert _sep_arcsec(_sky(moved, cx, cy), _sky(src, DOT_X, DOT_Y)) < 1.0

    from seestack.io.wcs_io import arcsec_per_px
    # Half the pixels across the same sky ⇒ twice the arcsec per pixel.
    assert arcsec_per_px(wcs_from_text(moved).celestial) == pytest.approx(
        arcsec_per_px(wcs_from_text(src).celestial) / scale, rel=0.02)


def test_crop_then_resize_compose():
    src = make_synth_wcs_text(width=W, height=H)
    ops = [{"id": "geometry.crop", "params": {"x0": 0.1, "x1": 0.9,
                                              "y0": 0.15, "y1": 0.85}},
           {"id": "geometry.resize", "params": {"scale": 0.6}}]
    img = _dot_image()
    for o in ops:
        img = _apply(o["id"], img, o["params"])
    cx, cy = _centroid(img)

    moved = wcs_text_after_pixel_steps(
        src, geometry_pixel_steps(recipe_from_dict({"ops": ops}), (H, W)))
    assert moved is not None
    assert _sep_arcsec(_sky(moved, cx, cy), _sky(src, DOT_X, DOT_Y)) < 1.0


def test_a_rotated_pc_matrix_survives_a_resize():
    """The scale factors multiply the transform's *columns* (pixel axes), not its
    rows — the same thing only on a diagonal matrix. A field rotation makes the
    two answers differ, so pin the star rather than the keywords."""
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [83.6, -5.4]
    w.wcs.crpix = [W / 2 + 0.5, H / 2 + 0.5]
    w.wcs.cdelt = [-5.0 / 3600.0, 5.0 / 3600.0]
    th = np.radians(23.0)
    w.wcs.pc = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    src = str(w.to_header(relax=True))

    params = {"scale": 0.5}
    out = _apply("geometry.resize", _dot_image(), params)
    cx, cy = _centroid(out)
    moved = wcs_text_after_pixel_steps(
        src, geometry_pixel_steps(
            recipe_from_dict({"ops": [{"id": "geometry.resize", "params": params}]}),
            (H, W)))
    assert moved is not None
    assert _sep_arcsec(_sky(moved, cx, cy), _sky(src, DOT_X, DOT_Y)) < 1.0


def test_a_resize_drops_a_sip_solution_rather_than_leaving_it_wrong():
    """SIP coefficients are polynomials in *source* pixels. A crop only shifts the
    origin they are already relative to, so they stay valid; a rescale does not, and
    a silently-wrong distortion is worse than no solution."""
    from astropy.io.fits import Header

    hdr = Header.fromstring(make_synth_wcs_text(width=W, height=H))
    hdr["CTYPE1"] = "RA---TAN-SIP"
    hdr["CTYPE2"] = "DEC--TAN-SIP"
    hdr["A_ORDER"] = 2
    hdr["B_ORDER"] = 2
    hdr["A_2_0"] = 1e-6
    hdr["B_0_2"] = 1e-6
    text = str(hdr)

    assert wcs_text_after_pixel_steps(text, [("crop", 40, 30)]) is not None
    assert wcs_text_after_pixel_steps(text, [("resize", W, H, W // 2, H // 2)]) is None
