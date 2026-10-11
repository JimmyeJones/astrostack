"""Star mask + star-mask-aware editor ops."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("scipy")

from seestack.edit.registry import EditContext, get_op
from seestack.edit.starmask import star_mask


def _star_and_nebula(h=80, w=80):
    """A scene with a faint extended blob (nebula) and a few sharp stars."""
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.full((h, w), 0.05, dtype=np.float32)
    # Broad smooth nebula in the centre.
    img += 0.3 * np.exp(-(((xx - w / 2) / 18) ** 2 + ((yy - h / 2) / 18) ** 2))
    # A few compact bright stars.
    stars = [(15, 20), (60, 25), (40, 65)]
    for (sy, sx) in stars:
        img += 0.9 * np.exp(-(((xx - sx) / 1.0) ** 2 + ((yy - sy) / 1.0) ** 2))
    rgb = np.stack([img, img, img], axis=-1)
    return np.clip(rgb, 0, 1), stars


def test_star_mask_hot_on_stars_cold_on_nebula():
    rgb, stars = _star_and_nebula()
    m = star_mask(rgb, size_px=3.0)
    assert m.shape == rgb.shape[:2]
    assert m.min() >= 0 and m.max() <= 1.0
    # High at a star, low at the nebula centre.
    for (sy, sx) in stars:
        assert m[sy, sx] > 0.4, (sy, sx, m[sy, sx])
    assert m[40, 40] < 0.2  # nebula core


def test_star_mask_handles_nan_coverage():
    rgb, _ = _star_and_nebula()
    rgb = rgb.copy()
    rgb[:10, :, :] = np.nan
    m = star_mask(rgb, size_px=3.0)
    assert np.isfinite(m).all()
    assert (m[:10, :] == 0).all()  # uncovered → 0


def test_star_mask_empty_image_is_zero():
    rgb = np.full((20, 20, 3), np.nan, dtype=np.float32)
    m = star_mask(rgb, size_px=3.0)
    assert (m == 0).all()


def test_reduce_dims_stars_more_than_nebula():
    rgb, stars = _star_and_nebula()
    spec = get_op("stars.reduce")
    out = spec.apply(rgb, {"amount": 1.0, "size": 2}, EditContext())
    # Stars should drop noticeably.
    for (sy, sx) in stars:
        assert out[sy, sx, 0] < rgb[sy, sx, 0] - 0.1
    # Nebula core should be essentially preserved (protected by the mask).
    assert abs(out[40, 40, 0] - rgb[40, 40, 0]) < 0.05


def test_reduce_protect_off_still_runs():
    rgb, _ = _star_and_nebula()
    spec = get_op("stars.reduce")
    out = spec.apply(rgb, {"amount": 0.5, "size": 2, "protect_nebula": False}, EditContext())
    assert out.shape == rgb.shape
    assert np.isfinite(out).all()


def test_boost_nebula_lifts_background_not_stars():
    rgb, stars = _star_and_nebula()
    spec = get_op("stars.boost_nebula")
    out = spec.apply(rgb, {"amount": 0.8, "size": 4}, EditContext())
    # Nebula region brightens.
    assert out[40, 40, 0] > rgb[40, 40, 0] + 0.02
    # Star cores barely move.
    for (sy, sx) in stars:
        assert abs(out[sy, sx, 0] - rgb[sy, sx, 0]) < 0.1


def test_boost_nebula_zero_amount_is_noop():
    rgb, _ = _star_and_nebula()
    spec = get_op("stars.boost_nebula")
    out = spec.apply(rgb, {"amount": 0.0}, EditContext())
    np.testing.assert_allclose(out, rgb, atol=1e-6)


def test_ops_registered_in_schema():
    from seestack.edit.registry import all_specs
    ids = {s.id for s in all_specs()}
    assert "stars.boost_nebula" in ids


# --- the whole-picture references, and the window that borrows them ----------
#
# ``star_mask`` normalises twice against the *whole array*: ``hi``, the 99.9th
# percentile of the white top-hat, and the mask's own post-blur peak. The editor's
# "check it at full size" loupe renders one 512 px window at ``proxy_scale = 1``
# and freezes the whole-image render's measurements onto it — and "star reduction
# differs on the preview" is one of the four advisories that control exists to
# answer. Until v0.493.5 the star mask was not on the frozen list, so the window
# built its mask from its own brightest pixel. These pin the fix and the control
# that shows the fixture can exhibit it.

_WIN = 512
_HI_KEY = "u1:star_tophat_hi:4"
_PEAK_KEY = "u1:star_mask_peak:4:0.5"


def _mosaic_canvas(h=1000, w=1100, seed=7):
    """A canvas whose star population is *not* uniform — a dense cluster around a
    bright core in one corner and a nearly starless far side, which is the ordinary
    shape of a tiled mosaic and the only shape that can show this at all."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = 0.010 + 0.004 * (xx / w)                      # a gentle sky gradient
    img += 0.9 * np.exp(-(((yy - 190) / 120.0) ** 2 + ((xx - 230) / 140.0) ** 2))
    for cy, cx, n, amp, sig in ((190, 230, 300, 1.2, 130.0),
                                (780, 850, 40, 0.06, 150.0)):
        ys = rng.normal(cy, sig, n)
        xs = rng.normal(cx, sig, n)
        for y, x, a in zip(ys, xs, rng.uniform(0.05, amp, n), strict=True):
            y0, x0 = int(y), int(x)
            if not (6 <= y0 < h - 7 and 6 <= x0 < w - 7):
                continue
            gy, gx = np.mgrid[y0 - 6:y0 + 7, x0 - 6:x0 + 7]
            img[y0 - 6:y0 + 7, x0 - 6:x0 + 7] += a * np.exp(
                -(((gy - y) ** 2 + (gx - x) ** 2) / (2 * 1.3 ** 2)))
    img += rng.normal(0, 0.0015, img.shape)
    rgb = np.stack([img * 1.02, img, img * 0.97], axis=-1).astype(np.float32)
    return np.clip(rgb, 0.0, 1.0)


#: A window of plain far side — a few faint stars, no bright core. Deliberately
#: *not* on the interesting part: see
#: ``test_a_windows_own_reference_is_wrong_in_both_directions`` for why the dim
#: window is the one that matters.
_DIM = (slice(470, 470 + _WIN), slice(560, 560 + _WIN))
_BRIGHT = (slice(0, _WIN), slice(0, _WIN))


def _apply(op_id, params, rgb, *, scale=1.0, frozen=None, uid="u1"):
    spec = get_op(op_id)
    ctx = EditContext(proxy_scale=scale, is_proxy=scale > 1.0, stage="nonlinear",
                      op_uid=uid, frozen_fits=frozen)
    return spec.apply(np.ascontiguousarray(rgb),
                      {**spec.defaults(), **params}, ctx), ctx


def _rel(window, truth):
    """Mean |difference| as a share of the window's own 99th-percentile level, so
    the number reads as "how far off is this picture" rather than "how bright"."""
    cov = np.isfinite(truth).all(axis=2)
    ref = float(np.nanpercentile(np.abs(truth[cov]), 99.0)) or 1.0
    return float(np.nanmean(np.abs(window - truth)[cov])) / ref


def _refs(arr, scale=1.0):
    ctx = EditContext(op_uid="u1", proxy_scale=scale, is_proxy=scale > 1.0)
    star_mask(np.ascontiguousarray(arr), size_px=4.0, ctx=ctx)
    return ctx.fitted


def test_star_mask_records_both_whole_picture_references():
    fitted = _refs(_mosaic_canvas(h=200, w=240))
    assert set(fitted) == {_HI_KEY, _PEAK_KEY}
    assert fitted[_HI_KEY] > 0


def test_star_mask_reuses_a_frozen_reference_instead_of_measuring_it():
    rgb = _mosaic_canvas(h=200, w=240)
    own = star_mask(rgb, size_px=4.0, ctx=EditContext(op_uid="u1"))
    fitted = _refs(rgb)
    # Ten times the reference: the top-hat is divided by it, so every weight must
    # fall. If the frozen value were ignored the two masks would be identical.
    loud = star_mask(rgb, size_px=4.0, ctx=EditContext(
        op_uid="u1", frozen_fits={**fitted, _HI_KEY: fitted[_HI_KEY] * 10.0}))
    assert loud.sum() < own.sum() * 0.9


def test_the_reference_key_is_the_full_resolution_footprint_not_the_scaled_one():
    """The whole-image render is usually the *decimated* proxy and the window that
    borrows from it is 1:1, so a key derived from the pixel footprint (1 px against
    4) would never match. ``size_px`` is a full-resolution measure, equal at both."""
    rgb = _mosaic_canvas(h=300, w=400)
    assert set(_refs(rgb[::3, ::3], scale=3.0)) == set(_refs(rgb))


def test_a_mask_with_no_context_is_the_mask_the_channel_measures():
    """Every whole-image render — the live preview and the export both — supplies
    no frozen fits, so nothing either of them draws may move by a bit."""
    rgb = _mosaic_canvas(h=240, w=320)
    assert np.array_equal(star_mask(rgb, size_px=4.0),
                          star_mask(rgb, size_px=4.0, ctx=EditContext(op_uid="u1")))


def test_freezing_a_renders_own_references_back_onto_it_changes_nothing():
    rgb = _mosaic_canvas(h=240, w=320)
    ctx = EditContext(op_uid="u1")
    first = star_mask(rgb, size_px=4.0, ctx=ctx)
    second = star_mask(rgb, size_px=4.0,
                       ctx=EditContext(op_uid="u1", frozen_fits=ctx.fitted))
    assert np.array_equal(first, second)


def test_a_windows_own_reference_is_wrong_in_both_directions():
    """Why this cannot be patched with a floor or a cap on the window's own
    measurement: on this canvas (reference 0.332) a dim window measures **0.026**
    and a window over the cluster **0.633**, while the whole *decimated proxy*
    measures 0.330 — within 1 % of the picture's own. The picture's number is the
    only one that is right, which is exactly what ``fit`` carries."""
    rgb = _mosaic_canvas()
    whole = _refs(rgb)[_HI_KEY]
    proxy = _refs(rgb[::3, ::3], scale=3.0)[_HI_KEY]
    assert abs(proxy - whole) / whole < 0.05
    assert _refs(rgb[_DIM])[_HI_KEY] < whole * 0.2
    assert _refs(rgb[_BRIGHT])[_HI_KEY] > whole * 1.4


@pytest.mark.parametrize(("op_id", "params", "unfrozen_at_least"), [
    # Measured on this fixture, as a share of the window's own 99th-percentile
    # level: re-measuring on the dim window puts stars.reduce **0.0071** out and
    # stars.boost_nebula **0.0205**, where freezing lands at 0.000000 and 0.000001.
    # The bars sit under the measurement so a kinder fixture fails this control
    # rather than passing the property below for free.
    ("stars.reduce", {"amount": 0.6, "size": 2}, 0.004),
    ("stars.boost_nebula", {"amount": 0.4, "size": 4}, 0.012),
])
def test_an_unfrozen_window_disagrees_with_the_picture_it_came_from(
        op_id, params, unfrozen_at_least):
    """The control. Re-running the op over a window — what the loupe would do if it
    simply set ``proxy_scale = 1`` — gives a visibly different picture from the same
    pixels in the whole render."""
    rgb = _mosaic_canvas()
    whole, _ = _apply(op_id, params, rgb)
    loose, _ = _apply(op_id, params, rgb[_DIM])
    err = _rel(loose, whole[_DIM])
    assert err > unfrozen_at_least, f"window is already faithful ({err:.6f})"


@pytest.mark.parametrize(("op_id", "params"), [
    ("stars.reduce", {"amount": 0.6, "size": 2}),
    ("stars.boost_nebula", {"amount": 0.4, "size": 4}),
])
def test_a_window_frozen_from_the_decimated_proxy_matches_the_full_render(op_id, params):
    """The property the loupe rests on, in the shape the loupe actually has: the
    references come off the *decimated* whole-image render, the window is 1:1."""
    rgb = _mosaic_canvas()
    whole, _ = _apply(op_id, params, rgb)
    _, pctx = _apply(op_id, params, rgb[::3, ::3], scale=3.0)
    frozen, _ = _apply(op_id, params, rgb[_DIM], frozen=pctx.fitted)
    loose, _ = _apply(op_id, params, rgb[_DIM])
    truth = whole[_DIM]
    assert _rel(frozen, truth) < 0.001
    # And strictly better than re-measuring, which is the claim being made.
    assert _rel(frozen, truth) < _rel(loose, truth) / 4.0
